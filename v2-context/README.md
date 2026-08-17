# L2 — Context Layer（上下文维护层）

> **定位**：L1 定义了"应该是什么"——但如果上下文膨胀，这些定义会被噪声稀释。L2 做一件事：**维护"模型现在记得什么"，在有限 token 预算内让关键信息不沉底。**

在 L1（Prompt → 定义应然）和 L3（State → 结构化行动）之间，用结构化提取 + 摘要注入 + 输出后处理，让模型在长对话中保持对约束和事实的记忆。

---

## 1. 它做了什么（流程图）

```
                        ┌──────────────────────┐
                        │   Raw Conversation    │
                        │   40轮, ~12K tokens   │
                        │   (含闲聊、试错、重复)  │
                        └──────────┬───────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │   Memory Extractor   │
                        │   (LLM 驱动的提取器)  │
                        │                      │
                        │  提取 → 分类 → 标记   │
                        │  事实 / 约束 / 决策    │
                        │  待办 / 进度 / 疑问    │
                        └──────────┬───────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │   State Summary      │
                        │   (结构化 JSON)       │
                        │                      │
                        │  ┌─────────────────┐ │
                        │  │ 事实层 (fact)    │ │
                        │  │ • 约束           │ │
                        │  │ • 决策           │ │
                        │  │ • 关键事实       │ │
                        │  ├─────────────────┤ │
                        │  │ 待办层 (pending) │ │
                        │  │ • 任务进度       │ │
                        │  │ • 未解疑问       │ │
                        │  └─────────────────┘ │
                        └──────────┬───────────┘
                                   │
                                   ▼
              ┌────────────────────────────────────┐
              │        Next Round Context          │
              │                                    │
              │  [System Prompt]                   │
              │  + [State Summary ~500 tokens]     │
              │  + [最近 3 轮原始对话 ~800 tokens]  │
              │  = ~1.3K tokens（替代 12K 原始）     │
              └────────────────────────────────────┘
```

### ⚠️ 风险提示：摘要器本身也可能漂移

上述流程中，**Memory Extractor 本身也是一个 LLM 调用**。当对话超过一定轮次、上下文噪声足够大时，提取器也可能提取出错误信息、遗漏关键更新、甚至编造不存在的事实。

这是 v2.5 的**根本矛盾**——用 LLM 来治理 LLM 的漂移，但治理者自己也在漂移风险之中。

### 我们采取的缓解措施

| 策略 | 说明 |
|------|------|
| **结构化字段 > 自然语言摘要** | Schema 强制输出 JSON 结构（事实列表/待办列表/决策列表），限制模型的"自由发挥"空间。自然语言极易引入轻微偏差，多次压缩后偏差放大。 |
| **`still_valid` 标记** | 每个约束和事实都标注是否仍然有效。被后续轮次推翻的旧信息不会悄无声息地存活在摘要中。 |
| **`confidence` 三级标注** | 事实分 `confirmed` / `tentative` / `disputed`。下游使用时可以只信任 `confirmed` 级别。 |
| **`source_turns` 溯源** | 每个提取条目记录来源轮次。人工审查时可以定位原始对话验证。 |
| **增量压缩优先** | 如果已有上一次的 state summary，使用增量模式（只分析新增轮次），而非每次重新扫描全部历史。这减少了提取器面对超长上下文的机会。 |
| **保留最近 3 轮原文** | 摘要之外始终附带最近 3 轮原始对话——这是"兜底"：即使摘要出错，最近对话的原始信息仍在上下文中。 |

---

## 2. State Summary 的 Schema 设计

这是 v2.5 最值得仔细读的部分。Schema 设计决定了信息在多次压缩后是否还能保持忠实。

Schema 文件：[`state_summary_schema.json`](./state_summary_schema.json)

### 两层结构

```
State Summary
│
├── 事实层 (fact layer) — 尽量结构化，减少二次幻觉空间
│   ├── active_constraints[]  约束与规则（format / content / behavior / domain）
│   │   ├── still_valid       是否仍有效（被后续推翻 → false）
│   │   ├── established_at    建立的轮次
│   │   └── invalidated_at    失效的轮次
│   │
│   ├── key_facts[]           已确立的关键事实
│   │   ├── confidence        confirmed | tentative | disputed
│   │   └── source_turns      来源轮次（可溯源验证）
│   │
│   └── decisions[]           已做出的决策
│       ├── decided_at        决策轮次
│       └── rationale         决策理由（防止后续重复讨论）
│
├── 待办层 (pending layer) — 当前任务进度和未解决的问题
│   ├── pending_items[]       待处理事项
│   │   ├── status            not_started | in_progress | blocked
│   │   ├── priority          high | medium | low
│   │   └── raised_at         提出的轮次
│   │
│   └── (implied)             未在 schema 显式列出、但提取 prompt 要求捕获：
│       └── unresolved_questions  用户提出但尚未回答的疑问
│
├── 元信息
│   ├── summary                3-5 句自然语言摘要（辅助人类阅读，非机器依赖）
│   ├── drift_indicators       漂移评分（可选，用于监控）
│   └── previous_compression_ref  指向上次压缩的 UUID（追溯链）
│
└── 对话统计
    ├── total_turns_processed  已处理总轮数
    ├── turn_range             本轮压缩覆盖的轮次范围
    └── token 统计             压缩前后的 token 数
```

### 为什么事实层用结构化字段而非自然语言段落

假设第 40 轮时摘要器产生了一段自然语言摘要：

> "用户正在使用 Python SDK v2.1.3 集成 API，数据库是 MySQL 8.0，之前遇到过 403 权限问题已解决，时区设置为 Asia/Shanghai，导出格式支持 CSV 和 Parquet..."

第 60 轮时的摘要器看到这段自然语言，可能把 "MySQL 8.0" 误解为 "PostgreSQL"、把 "已解决" 误写为 "仍在排查"、或者遗漏时区设置。**自由文本的每一次重述都是一次微小的语义漂移机会。**

而结构化字段：

```json
{
  "active_constraints": [
    {"content": "使用 Python SDK v2.1.3", "still_valid": true, "established_at_turn": 2},
    {"content": "数据库为 MySQL 8.0", "still_valid": true, "established_at_turn": 15}
  ],
  "key_facts": [
    {"content": "403 由 /data/export 缺少 Data Export 权限引起", "confidence": "confirmed", "source_turns": [3, 4]},
    {"content": "时区设置为 Asia/Shanghai (UTC+8)", "confidence": "confirmed", "source_turns": [9]}
  ],
  "decisions": [
    {"content": "短期不迁移 PostgreSQL，继续使用 MySQL 8.0", "decided_at_turn": 15, "rationale": "线上已稳定运行"}
  ]
}
```

每条信息独立存在、有来源、有状态标记。摘要器只需要做"增删改"操作——新增事实、标记旧事实失效、更新约束状态——而不需要用自己的语言重新描述一遍。**这大幅降低了二次漂移的风险。**

---

## 3. 集成方式：最小可运行示例

### 完整流水线

```python
"""
最小可运行示例：对话历史压缩 → 注入下一轮 system prompt

依赖：
    pip install openai  # 或其他 LLM SDK
    # memory_extractor.py 为本目录文件，无需额外安装
"""

import json
import os
from memory_extractor import MemoryExtractor, estimate_tokens, CompressedContext

# ============================================================
# Step 1: 加载对话历史
# ============================================================

def load_conversation(path: str) -> list[dict]:
    """从 JSON 文件加载对话历史"""
    with open(path) as f:
        return json.load(f)

# 示例对话文件格式（conversation.json）：
# [
#   {"role": "system", "content": "你是高可靠性助手..."},
#   {"role": "user", "content": "帮我分析..."},
#   {"role": "assistant", "content": "好的..."},
#   ...
# ]

# ============================================================
# Step 2: 调用 LLM 执行提取（你需要实现这个函数）
# ============================================================

def call_llm_for_extraction(prompt: str, conversation_text: str) -> dict:
    """
    用你的 LLM 执行提取。

    这是整个流水线中唯一需要你适配的部分——
    根据你使用的 LLM SDK（OpenAI / Anthropic / 本地模型）实现此函数。

    返回格式（与 state_summary_schema.json 一致）：
    {
        "constraints": [
            {"id": "c1", "content": "...", "established_at_turn": 2,
             "category": "behavior", "still_valid": true}
        ],
        "key_facts": [
            {"id": "f1", "content": "...", "source_turns": [3, 4],
             "confidence": "confirmed"}
        ],
        "decisions": [
            {"id": "d1", "content": "...", "decided_at_turn": 15,
             "rationale": "..."}
        ],
        "pending_items": [
            {"id": "p1", "content": "...", "raised_at_turn": 20,
             "status": "in_progress", "priority": "high"}
        ],
        "summary": "3-5 句自然语言摘要..."
    }
    """
    # --- 以 OpenAI 为例 ---
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    full_prompt = f"{prompt}\n\n## Conversation\n{conversation_text}"

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.1,  # 低温度：提取任务不需要创造性
        response_format={"type": "json_object"},  # 强制 JSON 输出
    )
    return json.loads(response.choices[0].message.content)

# ============================================================
# Step 3: 组装压缩上下文
# ============================================================

def build_compressed_context(
    extraction_result: dict,
    recent_turns: list[dict],
) -> dict:
    """
    将 LLM 提取结果 + 最近 N 轮原始对话 拼接为下一轮的上下文。
    """
    # 分类整理
    constraints = [
        c for c in extraction_result.get("constraints", [])
        if c.get("still_valid", True)
    ]
    facts = [
        f for f in extraction_result.get("key_facts", [])
        if f.get("confidence") in ("confirmed", "tentative")
    ]
    decisions = extraction_result.get("decisions", [])
    pending = extraction_result.get("pending_items", [])

    return {
        "summary": extraction_result.get("summary", ""),
        "constraints": constraints,
        "facts": facts,
        "decisions": decisions,
        "pending": pending,
        "recent_turns": recent_turns,
    }

# ============================================================
# Step 4: 拼接进下一轮 system prompt
# ============================================================

def format_for_next_round(compressed: dict, original_system_prompt: str) -> str:
    """
    将压缩上下文格式化为下一轮的 system prompt。

    这是最终注入 LLM 的内容。
    """
    parts = [original_system_prompt, "", "---", ""]

    # 事实层
    parts.append("## 对话状态摘要（由压缩器生成）")
    parts.append(compressed["summary"])

    if compressed["constraints"]:
        parts.append("\n### 活跃约束")
        for c in compressed["constraints"]:
            turn = c.get("established_at_turn", "?")
            parts.append(f"- [T{turn}] {c['content']}")

    if compressed["facts"]:
        parts.append("\n### 已确立的关键事实")
        for f in compressed["facts"]:
            turns = f.get("source_turns", ["?"])
            confidence = f.get("confidence", "tentative")
            marker = {"confirmed": "✅", "tentative": "⚠️", "disputed": "❌"}.get(confidence, "")
            parts.append(f"- {marker} [T{','.join(map(str, turns))}] {f['content']}")

    if compressed["decisions"]:
        parts.append("\n### 已做出的决策")
        for d in compressed["decisions"]:
            parts.append(f"- [T{d.get('decided_at_turn', '?')}] {d['content']}")

    # 待办层
    if compressed["pending"]:
        parts.append("\n### 待处理事项")
        for p in compressed["pending"]:
            status_icon = {"not_started": "⬜", "in_progress": "🔄", "blocked": "🚫"}.get(
                p.get("status"), "⬜"
            )
            parts.append(f"- {status_icon} [{p.get('priority', 'medium')}] {p['content']}")

    parts.append("\n---")
    parts.append("## 最近对话（保留原文）")

    for turn in compressed["recent_turns"]:
        role = turn.get("role", "unknown").capitalize()
        content = turn.get("content", "")
        if len(content) > 500:
            content = content[:500] + "..."
        parts.append(f"\n**{role}**: {content}")

    parts.append("\n---")
    parts.append("以上为压缩后的上下文。请基于这些信息回复用户的下一轮消息。")
    parts.append("如果发现摘要中的信息与最近对话原文矛盾，以原文为准。")

    return "\n".join(parts)

# ============================================================
# 主流程
# ============================================================

def main(conversation_path: str, system_prompt: str) -> str:
    """
    完整压缩流水线。

    Args:
        conversation_path: 对话历史 JSON 文件路径
        system_prompt: 原始系统提示词

    Returns:
        下一轮可用的完整 system prompt 字符串
    """
    # 1. 加载
    conversation = load_conversation(conversation_path)

    # 2. 检查是否需要压缩
    extractor = MemoryExtractor(max_recent_turns=3)
    tokens = estimate_tokens(conversation)
    turn_count = len([m for m in conversation if m["role"] != "system"]) // 2

    if not extractor.should_compress(turn_count, tokens):
        print(f"跳过压缩：{turn_count} 轮, {tokens} tokens 未达阈值")
        return system_prompt

    # 3. 构建提取请求
    extraction_data = extractor.extract(conversation)

    # 4. 调用 LLM 执行提取
    llm_result = call_llm_for_extraction(
        extraction_data["prompt"],
        extraction_data["conversation"],
    )

    # 5. 保留最近 3 轮原始对话
    recent = conversation[-6:]  # 3 轮 × 2 条（user + assistant）

    # 6. 组装
    compressed = build_compressed_context(llm_result, recent)

    # 7. 输出 state_summary.json（用于审查和追溯）
    with open("state_summary.json", "w", encoding="utf-8") as f:
        json.dump(compressed, f, ensure_ascii=False, indent=2)
    print("state_summary.json 已写入")

    # 8. 格式化下一轮 system prompt
    next_prompt = format_for_next_round(compressed, system_prompt)

    print(f"压缩完成：{turn_count} 轮 → {len(next_prompt.split())} 词")
    return next_prompt


if __name__ == "__main__":
    SYSTEM = "你是高可靠性 AI 助手，核心任务是帮助用户分析技术问题。"
    prompt = main("conversation.json", SYSTEM)
    # 将 prompt 作为下一轮 API 调用的 system prompt
```

### 输出文件示例（state_summary.json）

```json
{
  "summary": "用户在使用 Python SDK v2.1.3 集成 SaaS API。已解决 403 权限、时区、分页配置等问题。当前在讨论导出功能。",
  "constraints": [
    {"id": "c1", "content": "使用 Python SDK v2.1.3", "established_at_turn": 2, "category": "domain", "still_valid": true},
    {"id": "c2", "content": "数据库为 MySQL 8.0，暂不迁移", "established_at_turn": 15, "category": "domain", "still_valid": true}
  ],
  "facts": [
    {"id": "f1", "content": "/data/export 需要单独开启 Data Export 权限", "source_turns": [3, 4], "confidence": "confirmed"},
    {"id": "f2", "content": "参数名为 start/end 而非 start_date/end_date", "source_turns": [7], "confidence": "confirmed"},
    {"id": "f3", "content": "时区设置为 Asia/Shanghai", "source_turns": [9], "confidence": "confirmed"}
  ],
  "decisions": [
    {"id": "d1", "content": "使用轮询方式查询异步导出进度，不用 webhook", "decided_at_turn": 27, "rationale": "无公网端点"}
  ],
  "pending": [
    {"id": "p1", "content": "更新文档中的参数名 typo", "raised_at_turn": 29, "status": "not_started", "priority": "low"},
    {"id": "p2", "content": "提供 Parquet 大数据量导出的最佳实践", "raised_at_turn": 31, "status": "in_progress", "priority": "high"}
  ],
  "recent_turns": [
    {"role": "user", "content": "Parquet 导出 100 万行数据大概多久？"},
    {"role": "assistant", "content": "大约 2-5 分钟。使用 async_export_data() 可避免超时..."},
    {"role": "user", "content": "好的，那给我写个完整示例"}
  ]
}
```

---

## 4. 何时触发压缩

没有放之四海皆准的触发时机，需要在成本和效果间权衡。

### 触发条件

```python
def should_compress(
    turn_count: int,
    estimated_tokens: int,
    drift_score: float | None = None,
) -> bool:
    """三种触发条件，满足任一即触发"""
    # 条件 A：轮次硬阈值
    if turn_count >= 30:
        return True

    # 条件 B：token 软阈值（context window 的 70%）
    if estimated_tokens > context_window_size * 0.7:
        return True

    # 条件 C：漂移检测信号（来自 L1 自检或 stop_sequences 命中频率）
    if drift_score is not None and drift_score > 0.6:
        return True

    return False
```

### Trade-off 表

| 策略 | 优点 | 缺点 | 推荐场景 |
|------|------|------|----------|
| **每 10 轮固定触发** | 实现简单，可预测 | 短对话浪费 API 调用；高峰期可能延迟压缩 | 原型阶段，对话节奏稳定 |
| **token 阈值触发（>context×70%）** | 按需触发，不浪费 | 估算 token 数不精确（不同 tokenizer 差异大） | 生产环境推荐 |
| **漂移信号触发** | 最精准，只在需要时压缩 | 依赖漂移检测的准确性；检测本身可能漏报 | 有成熟漂移检测时使用 |
| **轮次阈值 + token 双条件** | 兜底 + 精准 | 逻辑稍复杂 | **推荐默认方案** |

### 压缩频率的代价

```
压缩频率：  每 5 轮          每 15 轮          每 30 轮

API 成本：  ██████████       ████              ██
压缩质量：  ██████████       ████████          ██████
                                              （累积噪声）
上下文精度：██████████       ████████          ██████
                                              （旧上下文已污染多轮）
推荐：      过于频繁          最佳平衡点         仅兜底
```

**建议**：从 `max(30轮, context×70%)` 出发，观察实际效果后微调。

---

## 5. 已知局限

### 局限 1：错误纠正可能被摘要器遗漏（静默传播）

**场景**：用户在第 10 轮纠正了一个错误事实（比如 "API 的 rate limit 是 1000/min 不是 500/min"）。摘要器在第 15 轮执行压缩时——如果提取 prompt 没有明确要求检查"是否存在对旧事实的更新"——摘要中可能仍然保留着 `rate_limit: 500/min`。

第 20 轮时，模型读到这个过时的摘要，基于错误信息给出回复。用户说"我不是纠正过你吗？"——这就是**静默错误传播**。

**当前缓解**：
- Schema 中 `still_valid` 字段 + `confidence: disputed` 标记
- 提取 prompt 明确要求"如果后续轮次修正了早期信息，标注旧事实为 still_valid: false"
- 保留的最近 3 轮原始对话是兜底（如果摘要错了，模型还有原文可参考）

**尚未解决**：摘要器本身执行这个"检查更新"任务时，它自己也可能漂移，漏掉更新。这是一个递归信任问题——你在用 LLM 检查 LLM 的工作。

### 局限 2：压缩信号滞后

压缩最多每 N 轮触发一次。在第 N−1 轮、快触发压缩但还没触发时，上下文中已经积累了 N−1 轮的噪声。这意味**着在压缩生效前，模型已经在噪声中工作了若干轮**。

**缓解**：降低 N 值（如 15 轮），但以增加 API 成本为代价。

### 局限 3：增量压缩的偏差累积

使用增量模式时（基于上一次的 state summary + 新增轮次），上一次 summary 中的微小偏差会被继承到下一轮 summary 中。多次增量压缩后，偏差可能被放大。

**缓解**：
- 至少每 3 次增量压缩后做一次全量重压缩
- 保留 `previous_compression_ref` 追溯链，便于审计

### 局限 4：结构化字段 ≠ 零幻觉

结构化 JSON 约束了输出格式，但不约束内容正确性。摘要器仍然可能把 "MySQL" 写成 "PostgreSQL"，只是现在这个错误被锁在 `"content"` 字段里，看起来更"可信"了。

**缓解**：对关键事实使用 `confidence: tentative` + `source_turns` 溯源，下游代码可以在 `confidence != "confirmed"` 时降级处理（如回退到原始对话）。

### 局限 5：高度依赖提取 prompt 质量

提取 prompt 的措辞变化可能导致提取结果的结构和完整性显著不同。这是 prompt 工程的固有问题。

**缓解**：使用 `state_summary_schema.json` 约束输出格式；在 prompt 中使用具体示例（few-shot）而非纯指令。

### 局限 6：不适合需要精确原文的场景

- 法律文书逐字审查
- 医疗诊断中的症状描述
- 代码审查中的具体行号引用

这些场景需要的是 **RAG + 原文引用**，而非上下文压缩。

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `memory_extractor.py` | MemoryExtractor 类 + CompressedContext 数据结构 + token 估算工具 |
| `state_summary_schema.json` | JSON Schema (2020-12)，标准化压缩输出格式 |
| `output_post_filter.py` | stop_sequences 输出后处理过滤器（通用平台兜底方案） |
| `examples/50_turn_demo.md` | 50 轮对话压缩前后对比（含真实漂移案例） |

---

## 与 L3 的关系

- L2 压缩效果下降（50+ 轮后摘要本身变长）→ 升级到 L3 State Machine，将压缩器嵌入状态转移逻辑
- 需要跨会话记忆 → L3 的 checkpoint 机制原生支持
- 对延迟敏感 → 将提取 LLM 换成轻量模型（如 GPT-4o-mini），提取任务不需要强推理能力
- stop_sequences 后处理在 L2 层，ALLOWED/FORBIDDEN 门控在 L3 层——两者互补：L2 做紧急截断，L3 做事前预防
