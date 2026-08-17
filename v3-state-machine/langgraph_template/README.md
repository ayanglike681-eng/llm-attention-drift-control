# LangGraph Drift Control Template

> 基于 LangGraph 的状态机模板。**先跑 `minimal_example.py`（5 分钟），再看完整版。**

---

## 两个版本，按需取用

| 文件 | 适合 | 内容 |
|------|------|------|
| [`minimal_example.py`](minimal_example.py) | 🔰 新用户 / 想快速看效果 | 3 状态（research → decision → done），硬编码所有配置，可直接跑 |
| [`advanced/drift_control_graph.py`](advanced/drift_control_graph.py) | 🔧 生产使用 / 需要完整功能 | 7 状态 + ALLOWED/FORBIDDEN prompt 注入 + drift recovery + checkpoint |

---

## 快速开始

```bash
pip install langgraph langchain-openai
export OPENAI_API_KEY="sk-..."
python minimal_example.py
```

终端会启动一个对话循环，输入消息看模型在不同状态下的行为变化。

---

## 状态图

```
RESEARCH ──→ DECISION ──→ DONE
   ↑             │
   └─────────────┘ (用户要求重新分析时回退)
```

完整版（advanced/）增加了 INIT、CLARIFY、VERIFYING、DRIFT_RECOVERY。

---

## 关键文件

| 文件 | 说明 |
|------|------|
| `minimal_example.py` | 最简可跑示例（从这里开始） |
| `advanced/drift_control_graph.py` | 完整状态机实现（7 状态 + STATE_PROMPTS） |
| 上级 `dify_template/` | Dify 可视化版本（零代码） |

---

## Checkpoint 机制

完整版内置 LangGraph checkpoint，对话中断或漂移时可恢复：

```python
from advanced.drift_control_graph import DriftControlGraph
controller = DriftControlGraph(llm=llm)
result = controller.resume(thread_id="conversation-001")
```
