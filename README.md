
---

## 切换模型

v4 设计：**一个配置 + 一个 provider 名字 = 切任意模型**。

### 支持的 Provider

| Provider | 默认 BaseURL | 默认 Model | 所需环境变量 |
|----------|-------------|-----------|------------|
| `agnes` | `https://apihub.agnes-ai.com/v1` | `agnes-1.5-flash` | `AGNES_API_KEY` |
| `qwen` | `https://ai.tdp.fan/api/v1` | `qwen3.6-35b-a3b` | `QWEN_API_KEY` |
| `openai` | (需手动设) | (需手动设) | `OPENAI_API_KEY` |
| `doubao` | (需手动设) | (需手动设) | 自定义 |
| `deepseek` | (需手动设) | (需手动设) | 自定义 |
| `ollama` | (需手动设) | (需手动设) | 自定义 |

### 用法

```bash
# Agnes（默认）
AGNES_API_KEY=*** ./deepin-agent --demo

# Qwen (TDP 镜像)
QWEN_API_KEY=*** LLM_PROVIDER=qwen ./deepin-agent --demo

# 自定义 BaseURL + Model（覆盖预设）
LLM_PROVIDER=qwen \
QWEN_API_KEY=*** \
LLM_BASE_URL=https://your-proxy.com/v1 \
LLM_MODEL=custom-model \
./deepin-agent chat "你的问题"
```

### Reasoning 模型注意

Qwen 3.6 是 reasoning 模型（带思考过程），`max_tokens=2000` 才能完整输出。
普通模型（Agnes/OpenAI 等）默认 100 token 够用。
