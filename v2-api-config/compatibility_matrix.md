# API 参数兼容性矩阵

> ⚠️ 此为补充参考。API 采样参数解决的是"模型输出了什么词"（症状），三层体系解决的是"模型在想什么"（病因）。两者维度不同。核心文档见 [`reference/api-params.md`](../reference/api-params.md)。

---

## 参数支持总览

| 参数 | OpenAI | Anthropic | Google Gemini | Azure OpenAI | vLLM / Ollama |
|------|--------|-----------|---------------|--------------|---------------|
| `temperature` | ✅ 0–2 | ✅ 0–1 | ✅ 0–2 | ✅ 0–2 | ✅ |
| `top_p` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `top_k` | ❌ | ✅ | ✅ | ❌ | ✅ |
| `frequency_penalty` | ✅ −2.0~2.0 | ❌ | ❌ | ✅ −2.0~2.0 | ⚠️ 部分 |
| `presence_penalty` | ✅ −2.0~2.0 | ❌ | ❌ | ✅ −2.0~2.0 | ⚠️ 部分 |
| `stop` / `stop_sequences` | ✅ ≤4 个 | ✅ | ✅ ≤5 个 | ✅ ≤4 个 | ✅ |
| `max_tokens` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `seed` | ✅ | ❌ | ❌ | ✅ | ⚠️ |

> `logit_bias` 已从此表移除。它是 OpenAI 独占的 token 级采样参数，只触及输出症状不触及认知偏移本质，不适合作为漂移控制的核心手段。

---

## 平台差异与替代方案

### Anthropic（无 frequency/presence penalty）

**替代方案 1：System Prompt 模拟**

```text
DO NOT repeat yourself. If you've already made a point, move on.
Each response should contribute NEW insights.
```

**替代方案 2：输出后处理过滤**

见 [`v2-context/output_post_filter.py`](../v2-context/output_post_filter.py) — 正则匹配跑题模式，截断后触发重试。

**替代方案 3：stop_sequences 截断**

见 [`v2-api-config/anthropic/stop_sequences_example.py`](./anthropic/stop_sequences_example.py)。

### Google Gemini

```python
generation_config = {
    "temperature": 0.3,
    "top_p": 0.9,
    "top_k": 40,
    "stop_sequences": ["[DRIFT]", "Human:", "Assistant:"],
}
```

### 开源模型（vLLM）

```python
sampling_params = {
    "temperature": 0.3,
    "top_p": 0.9,
    "frequency_penalty": 0.3,
    "presence_penalty": 0.2,
    "stop": ["[DRIFT]", "###"],
    "max_tokens": 2048,
}
```

---

## 各平台推荐配置速查

### OpenAI GPT-4o / GPT-4.1

```json
{
  "temperature": 0.3,
  "frequency_penalty": 0.3,
  "presence_penalty": 0.2,
  "top_p": 0.9,
  "stop": ["[DRIFT_DETECTED]"]
}
```

### Anthropic Claude (Sonnet 4.6 / Opus 4.8)

```json
{
  "temperature": 0.3,
  "top_p": 0.9,
  "max_tokens": 2048,
  "stop_sequences": ["[DRIFT_DETECTED]", "\n\nHuman:", "\n\nAssistant:"]
}
```

### Google Gemini 2.5

```json
{
  "temperature": 0.3,
  "top_p": 0.9,
  "top_k": 40,
  "stop_sequences": ["[DRIFT_DETECTED]"]
}
```

---

## 参数调优指南

| 症状 | 三层体系解法（优先） | API 参数辅助 |
|------|-------------------|-------------|
| 模型答非所问 | L1 prompt 自检 + L3 状态约束 | ↓ temperature |
| 重复相同内容 | L2 上下文压缩去重 | ↑ frequency_penalty |
| 频繁跑题 | L3 FORBIDDEN 门控 | ↓ temperature + stop_sequences |
| 遗忘早期指令 | L2 结构化摘要注入 | —（API 参数无法解决此问题） |
| 50+轮仍失控 | L3 State Machine | —（API 参数无法解决此问题） |
