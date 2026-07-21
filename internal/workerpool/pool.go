// Package workerpool 提供并发执行一组 Worker 的能力
//
// 对应 advisor-orchestrator-worker skill 的 "Delegate" 步骤：
// "Parallel background calls, then wait."
//
// 设计目标：
//   - 接收一组 Worker（每个 worker 是 (subtask_id, exec_fn) 的闭包）
//   - 并发跑，errgroup 失败传播
//   - 每个 worker 的状态独立判定（PASS / FIX / ESCALATE）
//   - 汇总到 PoolResult，方便 ledger 和 orchestrator 格式化输出
//
// 与现有 Orchestrator 不冲突——这是新增包，按需调用。
package workerpool

import (
	"context"
	"time"

	"golang.org/x/sync/errgroup"
)

// Verdict worker 的三态判定结果（与 agents.Verdict 同义但解耦，避免循环依赖）
type Verdict string

const (
	VerdictPass     Verdict = "PASS"
	VerdictFix      Verdict = "FIX"
	VerdictEscalate Verdict = "ESCALATE"
)

// Worker 一个独立的 subtask 单元。
//
//   - ID: ledger / 状态板标识
//   - Run: 真正执行的逻辑（必须接受 ctx 便于取消）
//   - Verify: 跑完后自带的 verifier，返回 (Verdict, Reason)
type Worker struct {
	ID      string
	Run     func(ctx context.Context) (any, error)
	Verify  func(report any, err error) (Verdict, string)
	Timeout time.Duration // 可选；0 = 不超时
}

// PoolResult 单个 worker 的运行结果
type PoolResult struct {
	WorkerID   string
	Report     any
	Verdict    Verdict
	Reason     string
	Err        error
	DurationMs int64
}

// Pool 一次并发执行的结果汇总
type Pool struct {
	Results      []*PoolResult
	TotalWorkers int
	Passed       int
	Fixed        int
	Escalated    int
	Failed       int // 底层 Run 报错数
	TotalMs      int64
}

// HasEscalation 用于 orchestrator 决定是否召 Advisor
func (p *Pool) HasEscalation() bool {
	return p != nil && p.Escalated > 0
}

// HasFailure FIX 或 ESCALATE 任一存在即视为不干净
func (p *Pool) HasFailure() bool {
	return p != nil && (p.Fixed > 0 || p.Escalated > 0)
}

// Run 并发跑一组 worker
//
// 失败策略：
//   - 任何一个 worker 的 Run 返回 err → 用 errgroup 取消其他，标记 Failed
//   - Run 成功但 Verify 判 FIX/ESCALATE → 不取消其他，verdict 计入统计
//   - 全部跑完后返回 Pool，无论结果好坏（除非 ctx 取消）
func Run(ctx context.Context, workers []Worker) (*Pool, error) {
	pool := &Pool{
		Results:      make([]*PoolResult, 0, len(workers)),
		TotalWorkers: len(workers),
	}

	results := make([]*PoolResult, len(workers))
	g, gctx := errgroup.WithContext(ctx)

	for i, w := range workers {
		i, w := i, w
		g.Go(func() error {
			start := time.Now()

			// 可选超时：用单独 ctx 不污染全局（worker 内部完成即解）
			runCtx := gctx
			if w.Timeout > 0 {
				var cancel context.CancelFunc
				runCtx, cancel = context.WithTimeout(gctx, w.Timeout)
				defer cancel()
			}

			report, err := w.Run(runCtx)

			result := &PoolResult{
				WorkerID:   w.ID,
				Report:     report,
				Err:        err,
				DurationMs: time.Since(start).Milliseconds(),
			}

			// Run 失败：fixed/escalated 不计；底层错误计入 Failed
			if err != nil {
				result.Verdict = VerdictEscalate
				result.Reason = "worker.Run error: " + err.Error()
			} else {
				v, reason := w.Verify(report, nil)
				result.Verdict = v
				result.Reason = reason
			}

			results[i] = result
			return err // 传给 errgroup 控制并发取消
		})
	}

	// 等全部跑完（errgroup 失败传播）
	if err := g.Wait(); err != nil {
		// 已被 errgroup 取消，把已收集结果合并到 pool.Results
		// 并返回 err 让上层感知
		pool.Results = collectNonNil(results)
		pool.aggregate()
		return pool, err
	}

	pool.Results = results
	pool.aggregate()
	return pool, nil
}

// aggregate 从 Results 汇总统计
func (p *Pool) aggregate() {
	for _, r := range p.Results {
		if r == nil {
			continue
		}
		p.TotalMs += r.DurationMs
		switch r.Verdict {
		case VerdictPass:
			p.Passed++
		case VerdictFix:
			p.Fixed++
		case VerdictEscalate:
			p.Escalated++
		}
		if r.Err != nil {
			p.Failed++
		}
	}
}

// collectNonNil errgroup 中途取消时，未启动的 worker 的 Result 仍是 nil，过滤掉
func collectNonNil(results []*PoolResult) []*PoolResult {
	out := make([]*PoolResult, 0, len(results))
	for _, r := range results {
		if r != nil {
			out = append(out, r)
		}
	}
	return out
}
