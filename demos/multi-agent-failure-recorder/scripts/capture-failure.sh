#!/usr/bin/env bash
# capture-failure.sh — demos/multi-agent-failure-recorder 的失败样本采集脚本
#
# 用法：
#   bash scripts/capture-failure.sh
#   或：
#   bash scripts/capture-failure.sh --mode=F1 --task="用户请求" --expected="..." --actual="..."
#
# 输出：
#   runs/<date>-failure-<n>.json (单个样本)
#   runs/timeline.txt (append 一行)
#
# === 本脚本示例特意展示的 3 件事 ===
# 1. 交互式收集失败信息，避免"事后凭印象写"
# 2. 自动检查 mode 合法性（F1-F5）
# 3. 写盘前确认文件名 + 检查 n 序号不冲突

set -euo pipefail

DATE=$(date +%Y-%m-%d)
HOUR=$(date +%H:%M:%S)
RUNS_DIR="runs"
TIMELINE="runs/timeline.txt"

# === 解析命令行 ===
MODE=""
SCENE=""
TASK=""
EXPECTED=""
ACTUAL=""
AGENTS_JSON=""
ROOT_CAUSE=""
SEVERITY="medium"
REPRODUCIBILITY="100%"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode=*) MODE="${1#*=}" ;;
    --scene=*) SCENE="${1#*=}" ;;
    --task=*) TASK="${1#*=}" ;;
    --expected=*) EXPECTED="${1#*=}" ;;
    --actual=*) ACTUAL="${1#*=}" ;;
    --agents=*) AGENTS_JSON="${1#*=}" ;;
    --root_cause=*) ROOT_CAUSE="${1#*=}" ;;
    --severity=*) SEVERITY="${1#*=}" ;;
    --reproducibility=*) REPRODUCIBILITY="${1#*=}" ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
  shift
done

# === 交互式问缺省字段 ===
ask() {
  local prompt="$1" varname="$2"
  if [ -z "${!varname:-}" ]; then
    echo -n "$prompt: " >&2
    read -r "$varname"
  fi
}

ask "mode (F1-F5)" MODE
ask "scene (项目/场景)" SCENE
ask "task (用户请求)" TASK
ask "expected (预期)" EXPECTED
ask "actual (实际)" ACTUAL
ask "agents_involved (e.g. [{\"role\":\"a\",\"model\":\"qwen\"}])" AGENTS_JSON
ask "root_cause_hypothesis (猜测根因)" ROOT_CAUSE
ask "severity (high/medium/low)" SEVERITY
ask "reproducibility (100%/intermittent/unique)" REPRODUCIBILITY

# === 校验 ===
if [[ ! "$MODE" =~ ^F[1-5]$ ]]; then
  echo "❌ mode 必须是 F1-F5"
  exit 1
fi

if [ -z "$AGENTS_JSON" ]; then
  AGENTS_JSON="[]"
fi

# === 计算序号 n ===
mkdir -p "$RUNS_DIR"
n=1
while [ -f "$RUNS_DIR/${DATE}-failure-${n}.json" ]; do
  n=$((n + 1))
done

# === 落盘 JSON ===
ID="${DATE}-failure-${n}"
OUT="$RUNS_DIR/${ID}.json"

cat > "$OUT" <<EOF
{
  "id": "${ID}",
  "captured_at": "${DATE}T${HOUR}+08:00",
  "mode": "${MODE}",
  "scene": "${SCENE}",
  "agents_involved": ${AGENTS_JSON},
  "task": "${TASK}",
  "expected": "${EXPECTED}",
  "actual": "${ACTUAL}",
  "root_cause_hypothesis": "${ROOT_CAUSE}",
  "severity": "${SEVERITY}",
  "reproducibility": "${REPRODUCIBILITY}",
  "tags": []
}
EOF

echo ""
echo "✅ 失败样本已写: $OUT"
echo ""

# === 追加 timeline ===
echo "${DATE} ${HOUR} · ${MODE} · ${SCENE} · ${ID} · ${TASK:0:30}..." >> "$TIMELINE"

echo "📝 timeline 已更新: $TIMELINE"
echo ""
echo "现在可以:"
echo "  cat $OUT        # 看完整样本"
echo "  tail -3 $TIMELINE  # 看时间线"
echo "  bash scripts/capture-failure.sh  # 采集下一个"