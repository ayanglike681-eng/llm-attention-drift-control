# API 采样参数速查

> ⚠️ 这不是独立的一层。`frequency_penalty`、`stop_sequences` 等 API 采样参数解决的是"模型输出了什么词"——症状层面的干预。本项目三层体系（Prompt / Context / State）解决的是"模型在想什么"——认知层面的干预。两者维度不同。此文件仅作为补充参考。

---

## 参数兼容性一览

| 参数 | OpenAI | Anthropic | Google Gemini | vLLM / Ollama |
|------|--------|-----------|---------------|---------------|
| `temperature` | ✅ 0–2 | ✅ 0–1 | ✅ 0–2 | ✅ |
| `top_p` | ✅ | ✅ | ✅ | ✅ |
| `top_k` | ❌ | ✅ | ✅ | ✅ |
| `frequency_penalty` | ✅ −2.0~2.0 | ❌ | ❌ | ⚠️ 部分 |
| `presence_penalty` | ✅ −2.0~2.0 | ❌ | ❌ | ⚠️ 部分 |
| `stop` / `stop_sequences` | ✅ ≤4 个 | ✅ | ✅ ≤5 个 | ✅ |
| `seed` | ✅ | ❌ | ❌ | ⚠️ |

> `logit_bias` 不在上表中——它是 OpenAI 独占的 token 级采样参数，普适性极低，且只触及输出症状不触及认知偏移。不建议作为漂移控制的核心手段。

---

## 什么时候用 API 参数

API 参数应该作为**辅助手段**配合三层体系使用，而非独立一层：

| 症状 | 三层体系的解法 | API 参数的辅助 |
|------|--------------|---------------|
| 模型反复说同一观点 | L2 压缩去重 | `frequency_penalty` ↑ 减少 token 重复 |
| 模型困在一个子话题 | L3 状态切换 | `presence_penalty` ↑ 推动话题多样性 |
| 模型跑题后长篇大论 | L3 状态门控（FORBIDDEN） | `stop_sequences` 紧急截断 |
| 模型输出格式崩坏 | L1 prompt 自检 + L3 VERIFYING | `temperature` ↓ 集中概率分布 |

---

## stop_sequences 通用配置

`stop_sequences` 是全平台支持的兜底手段。项目中的实现见 `v2-context/output_post_filter.py`。

```python
# 通用的防漂移 stop_sequences（所有平台适用）
STOP_SEQUENCES = [
    "[DRIFT_DETECTED]",       # 模型自我检测到偏离
    "\n\nHuman:",             # 防止模型幻想新的用户消息
    "\n\nAssistant:",         # 防止模型幻想自己的后续回复
    "\n\nUser:",              # 同上
]
```

---

## 各平台推荐配置

### OpenAI

```json
{
  "temperature": 0.3,
  "frequency_penalty": 0.3,
  "presence_penalty": 0.2,
  "top_p": 0.9,
  "stop": ["[DRIFT_DETECTED]"]
}
```

### Anthropic Claude

```json
{
  "temperature": 0.3,
  "top_p": 0.9,
  "max_tokens": 2048,
  "stop_sequences": ["[DRIFT_DETECTED]", "\n\nHuman:", "\n\nAssistant:"]
}
```

### Google Gemini

```json
{
  "temperature": 0.3,
  "top_p": 0.9,
  "top_k": 40,
  "stop_sequences": ["[DRIFT_DETECTED]"]
}
```

### vLLM / Ollama

```python
sampling_params = {
    "temperature": 0.3,
    "top_p": 0.9,
    "frequency_penalty": 0.3,
    "stop": ["[DRIFT]", "###"],
}
```
