# v2 — API 参数配置（已降级为参考）

> ⚠️ 此目录不再是独立的一层。API 采样参数（`frequency_penalty`、`stop_sequences` 等）解决的是"模型输出了什么词"——症状层面。而本项目三层体系（Prompt / Context / State）解决的是"模型在想什么"——认知层面。两者维度不同，不应混在同一分层体系里。

---

## 去哪找你要的东西

| 你原来在这里找的 | 现在去这里 |
|-----------------|-----------|
| 平台兼容性矩阵 | [`reference/api-params.md`](../reference/api-params.md) |
| `stop_sequences` 配置示例 | [`reference/api-params.md`](../reference/api-params.md) |
| 输出后处理过滤（logit_bias 替代方案） | [`v2-context/output_post_filter.py`](../v2-context/output_post_filter.py) |
| OpenAI payload 示例（`logit_bias` 已移除） | 本目录 `openai_compatible/payload_example.json`（仅作参考） |
| Anthropic stop_sequences 示例 | 本目录 `anthropic/stop_sequences_example.py`（仅作参考） |

---

## 为什么不把 API 参数作为独立一层

1. **受众窄**：`logit_bias` 只有 OpenAI 兼容接口支持，`frequency_penalty` 不支持 Anthropic。作为独立一层会把大部分用户挡在门外。
2. **概念混乱**：API 参数解决"症状"（token 选择），三层体系解决"病因"（认知偏移）。硬塞在一起是"为了凑够层数"。
3. **因果关系断裂**：Prompt → Context → State 是连续的因果链。API 参数是这条链上的旁路工具，与链上的任一环节都没有因果推进关系。

实际使用中，API 参数作为辅助手段配合三层体系即可，不需独立成层。
