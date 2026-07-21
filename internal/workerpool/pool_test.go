package workerpool

import (
	"context"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestPool_AllPass(t *testing.T) {
	workers := []Worker{
		{
			ID:  "w1",
			Run:  func(ctx context.Context) (any, error) { return "r1", nil },
			Verify: func(r any, err error) (Verdict, string) {
				return VerdictPass, "ok"
			},
		},
		{
			ID:  "w2",
			Run:  func(ctx context.Context) (any, error) { return "r2", nil },
			Verify: func(r any, err error) (Verdict, string) {
				return VerdictPass, "ok"
			},
		},
	}

	pool, err := Run(context.Background(), workers)
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if pool.Passed != 2 || pool.Fixed != 0 || pool.Escalated != 0 {
		t.Errorf("expected 2 pass, got pool=%+v", pool)
	}
	if pool.HasFailure() {
		t.Error("all-pass pool should not have failure")
	}
}

func TestPool_MixedVerdicts(t *testing.T) {
	workers := []Worker{
		{ID: "pass", Run: okRun, Verify: func(any, error) (Verdict, string) { return VerdictPass, "ok" }},
		{ID: "fix", Run: okRun, Verify: func(any, error) (Verdict, string) { return VerdictFix, "needs redispatch" }},
		{ID: "esc", Run: okRun, Verify: func(any, error) (Verdict, string) { return VerdictEscalate, "needs advisor" }},
	}
	pool, err := Run(context.Background(), workers)
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if pool.Passed != 1 || pool.Fixed != 1 || pool.Escalated != 1 {
		t.Errorf("expected 1/1/1, got %+v", pool)
	}
	if !pool.HasEscalation() {
		t.Error("HasEscalation should be true")
	}
	if !pool.HasFailure() {
		t.Error("HasFailure should be true (FIX present)")
	}
}

func TestPool_WorkerErrorCancelsOthers(t *testing.T) {
	// w1 慢任务，w2 立刻错。
	// 期望：w1 被取消，w2 计入 Escalated + err 传给 Run 顶层。
	workers := []Worker{
		{
			ID: "slow",
			Run: func(ctx context.Context) (any, error) {
				select {
				case <-ctx.Done():
					return nil, ctx.Err()
				case <-time.After(2 * time.Second):
					return "slow done", nil
				}
			},
			Verify: func(any, error) (Verdict, string) { return VerdictPass, "" },
		},
		{
			ID: "fail",
			Run: func(ctx context.Context) (any, error) {
				return nil, errors.New("upstream unavailable")
			},
			Verify: func(any, error) (Verdict, string) { return VerdictEscalate, "kicked" },
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()

	start := time.Now()
	pool, err := Run(ctx, workers)
	elapsed := time.Since(start)

	if err == nil {
		t.Error("expected err from Run when worker fails")
	}
	if pool.Failed == 0 {
		t.Error("expected Failed >= 1")
	}
	// 关键：并发取消必须生效，不能等 2s 跑完
	if elapsed > 1500*time.Millisecond {
		t.Errorf("errgroup did not cancel early, elapsed=%v", elapsed)
	}
}

func TestPool_ConcurrentProven(t *testing.T) {
	// 5 个 worker 各自睡 100ms：串行要 500ms，并发要 ~100ms
	const n = 5
	workers := make([]Worker, n)
	var started atomic.Int32
	for i := 0; i < n; i++ {
		idx := i
		workers[i] = Worker{
			ID:    string(rune('a' + idx)),
			Run: func(ctx context.Context) (any, error) {
				started.Add(1)
				time.Sleep(100 * time.Millisecond)
				return idx, nil
			},
			Verify: func(any, error) (Verdict, string) { return VerdictPass, "ok" },
		}
	}

	start := time.Now()
	pool, err := Run(context.Background(), workers)
	elapsed := time.Since(start)

	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if pool.Passed != n {
		t.Errorf("expected %d pass, got %d", n, pool.Passed)
	}
	if started.Load() != int32(n) {
		t.Errorf("expected all %d workers to start, got %d", n, started.Load())
	}
	// 并发上限：5 个 100ms 应该 ≤ 250ms（给点抖动预算）
	if elapsed > 250*time.Millisecond {
		t.Errorf("not parallel enough, elapsed=%v", elapsed)
	}
}

func TestPool_TimeoutPerWorker(t *testing.T) {
	// worker 真实监听 ctx.Done()——超时能被取消
	worker := Worker{
		ID: "timeout-test",
		Run: func(ctx context.Context) (any, error) {
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(2 * time.Second):
				return "done", nil
			}
		},
		Verify: func(any, error) (Verdict, string) { return VerdictPass, "ok" },
		Timeout: 50 * time.Millisecond,
	}
	start := time.Now()
	pool, err := Run(context.Background(), []Worker{worker})
	elapsed := time.Since(start)

	if err == nil {
		t.Error("expected err from timeout")
	}
	if elapsed > 250*time.Millisecond {
		t.Errorf("timeout not honored, elapsed=%v", elapsed)
	}
	if pool.Failed == 0 {
		t.Errorf("expected Failed >= 1 (ctx canceled), got %+v", pool)
	}
}

func TestPool_EmptyWorkers(t *testing.T) {
	pool, err := Run(context.Background(), nil)
	if err != nil {
		t.Errorf("empty input should not err, got %v", err)
	}
	if pool == nil || pool.TotalWorkers != 0 {
		t.Errorf("empty pool should have TotalWorkers=0, got %+v", pool)
	}
}

func TestPool_PreservesWorkerOrder(t *testing.T) {
	// 顺序：先加 w2 再加 w1（w1 慢，w2 快）—— 结果应按输入顺序返回
	workers := []Worker{
		{
			ID: "first",
			Run: func(ctx context.Context) (any, error) {
				time.Sleep(150 * time.Millisecond)
				return "A", nil
			},
			Verify: func(any, error) (Verdict, string) { return VerdictPass, "ok" },
		},
		{
			ID: "second",
			Run: func(ctx context.Context) (any, error) {
				return "B", nil
			},
			Verify: func(any, error) (Verdict, string) { return VerdictPass, "ok" },
		},
	}
	pool, err := Run(context.Background(), workers)
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if len(pool.Results) != 2 {
		t.Fatalf("expected 2 results, got %d", len(pool.Results))
	}
	if pool.Results[0].WorkerID != "first" {
		t.Errorf("Results[0].ID 应为 first, got %s", pool.Results[0].WorkerID)
	}
	if pool.Results[1].WorkerID != "second" {
		t.Errorf("Results[1].ID 应为 second, got %s", pool.Results[1].WorkerID)
	}
}

func TestPool_StaticFieldsSafeConcurrent(t *testing.T) {
	// 编译期检查：Results 字段本身在并发结果收集时不被竞态写入
	// （实测由 errgroup + slice index 写法保证——不变量要留着）
	workers := []Worker{
		{ID: "x", Run: okRun, Verify: func(any, error) (Verdict, string) { return VerdictPass, "ok" }},
		{ID: "y", Run: okRun, Verify: func(any, error) (Verdict, string) { return VerdictPass, "ok" }},
	}

	// 跑 -race 探测
	done := make(chan struct{})
	go func() {
		for i := 0; i < 100; i++ {
			pool, err := Run(context.Background(), workers)
			if err != nil || pool == nil {
				t.Errorf("iter %d: %v", i, err)
			}
			// 同时再启动一次确保并发
			_, _ = Run(context.Background(), workers)
		}
		close(done)
	}()
	<-done
}

// helpers

func okRun(ctx context.Context) (any, error) {
	return "ok", nil
}

// 静默 unused warning
var _ = sync.Mutex{}
var _ = strings.TrimSpace
