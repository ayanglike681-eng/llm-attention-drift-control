"""
Memory Extractor — 从长对话历史中提取和压缩关键信息

核心功能：
1. 从对话历史中提取关键事实、约束、决策
2. 生成结构化的对话状态摘要
3. 按优先级保留信息，丢弃噪声

使用方式：
    from memory_extractor import MemoryExtractor
    extractor = MemoryExtractor()
    compressed = extractor.compress(conversation_history)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Priority(Enum):
    """信息优先级"""
    CONSTRAINT = 1    # 约束与规则
    DECISION = 2      # 决策与结论
    FACT = 3          # 关键事实
    TODO = 4          # 待办事项
    CONTEXT = 5       # 上下文线索


@dataclass
class ExtractedItem:
    """提取的信息条目"""
    priority: Priority
    content: str
    source_turns: list[int]  # 来源于哪些轮次
    still_valid: bool = True  # 是否仍然有效（可能被后续更新覆盖）

    def to_dict(self) -> dict:
        return {
            "priority": self.priority.name,
            "content": self.content,
            "source_turns": self.source_turns,
            "still_valid": self.still_valid,
        }


@dataclass
class CompressedContext:
    """压缩后的上下文"""
    state_summary: str
    constraints: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    pending_items: list[str] = field(default_factory=list)
    recent_turns: list[dict] = field(default_factory=list)
    compression_metadata: dict = field(default_factory=dict)

    def format_for_llm(self) -> str:
        """将压缩上下文格式化为可直接注入 LLM 的文本"""
        parts = []

        if self.constraints:
            parts.append("## Active Constraints")
            for c in self.constraints:
                parts.append(f"- {c}")

        if self.key_facts:
            parts.append("\n## Key Facts Established")
            for f in self.key_facts:
                parts.append(f"- {f}")

        if self.decisions:
            parts.append("\n## Decisions Made")
            for d in self.decisions:
                parts.append(f"- {d}")

        if self.pending_items:
            parts.append("\n## Pending Items")
            for p in self.pending_items:
                parts.append(f"- [ ] {p}")

        if self.state_summary:
            parts.insert(0, f"## Conversation Summary\n{self.state_summary}")

        if self.recent_turns:
            parts.append("\n## Recent Conversation (last 3 turns)")
            for turn in self.recent_turns:
                role = turn.get("role", "unknown").capitalize()
                content = turn.get("content", "")
                # Truncate long messages
                if len(content) > 300:
                    content = content[:300] + "..."
                parts.append(f"\n**{role}**: {content}")

        return "\n".join(parts)


class MemoryExtractor:
    """
    对话记忆提取器。

    设计为与 LLM 交互的编排层——实际的提取逻辑由 LLM 完成，
    本类负责构造提取 prompt、解析结果、管理提取状态。
    """

    # 提取 prompt 模板
    EXTRACTION_PROMPT = """You are a conversation analyst. Extract the following from the conversation history:

1. **Constraints & Rules** (highest priority): Any rules, limitations, or format requirements the user set
2. **Decisions & Conclusions**: Agreements reached, choices made, conclusions drawn
3. **Key Facts**: Important information provided by the user
4. **Pending Items**: Unresolved questions, unfinished tasks
5. **State Summary**: A 3-5 sentence summary of the conversation's current state

For each extracted item, note which conversation turns it came from.
Mark items as "invalidated" if later turns override or contradict them.

Respond in the following JSON format:
{
  "constraints": [{"content": "...", "source_turns": [1, 2], "still_valid": true}],
  "decisions": [{"content": "...", "source_turns": [5], "still_valid": true}],
  "key_facts": [{"content": "...", "source_turns": [3, 7], "still_valid": true}],
  "pending_items": [{"content": "...", "source_turns": [10]}],
  "state_summary": "..."
}"""

    # 自检 prompt —— 用于增量提取
    INCREMENTAL_PROMPT = """Based on the PREVIOUS STATE SUMMARY below and the NEW conversation turns,
update the extracted information. Only include changes, additions, or invalidations.

PREVIOUS STATE:
{previous_state}

NEW TURNS:
{new_turns}

Respond with UPDATED JSON (full state, not just deltas)."""

    def __init__(
        self,
        max_recent_turns: int = 3,
        compression_threshold_tokens: int = 8000,
    ):
        """
        Args:
            max_recent_turns: 压缩后保留的最近原始对话轮数
            compression_threshold_tokens: 触发压缩的 token 阈值
        """
        self.max_recent_turns = max_recent_turns
        self.compression_threshold_tokens = compression_threshold_tokens
        self._last_extracted_items: list[ExtractedItem] = []

    def should_compress(
        self,
        turn_count: int,
        estimated_tokens: int,
        drift_indicators: Optional[dict] = None,
    ) -> bool:
        """
        判断是否应该触发压缩。

        Args:
            turn_count: 当前对话轮数
            estimated_tokens: 估计的上下文 token 数
            drift_indicators: 漂移指标（可选），如 {"repetition_rate": 0.3, "off_topic_score": 0.6}

        Returns:
            是否应该压缩
        """
        if turn_count > 30:
            return True
        if estimated_tokens > self.compression_threshold_tokens:
            return True
        if drift_indicators:
            off_topic = drift_indicators.get("off_topic_score", 0)
            repetition = drift_indicators.get("repetition_rate", 0)
            if off_topic > 0.6 or repetition > 0.4:
                return True
        return False

    def extract(
        self,
        conversation: list[dict],
        previous_state: Optional[CompressedContext] = None,
    ) -> list[ExtractedItem]:
        """
        从对话中提取关键信息。

        注意：此方法返回提取指令和对话数据，实际的 LLM 调用由上层完成。
        这里提供的是 prompt 构造和数据准备逻辑。

        Args:
            conversation: 对话历史 [{"role": "...", "content": "..."}, ...]
            previous_state: 上一次的压缩状态（用于增量提取）

        Returns:
            提取 prompt 和数据，供 LLM 处理
        """
        if previous_state:
            return self._build_incremental_extraction(conversation, previous_state)
        else:
            return self._build_full_extraction(conversation)

    def _build_full_extraction(self, conversation: list[dict]) -> dict:
        """构建完整提取的 prompt 和数据"""
        formatted = self._format_conversation(conversation)
        return {
            "prompt": self.EXTRACTION_PROMPT,
            "conversation": formatted,
            "mode": "full",
        }

    def _build_incremental_extraction(
        self,
        conversation: list[dict],
        previous_state: CompressedContext,
    ) -> dict:
        """构建增量提取的 prompt 和数据"""
        new_turns = conversation[-self.max_recent_turns * 2:]  # 新对话
        formatted_new = self._format_conversation(new_turns)
        prompt = self.INCREMENTAL_PROMPT.format(
            previous_state=previous_state.state_summary,
            new_turns=formatted_new,
        )
        return {
            "prompt": prompt,
            "conversation": formatted_new,
            "mode": "incremental",
            "previous_state": previous_state,
        }

    def compress(
        self,
        conversation: list[dict],
        extracted_items: list[ExtractedItem],
    ) -> CompressedContext:
        """
        将提取结果和对话历史合并为压缩上下文。

        Args:
            conversation: 完整对话历史
            extracted_items: 从 LLM 响应中解析的提取条目

        Returns:
            CompressedContext 对象
        """
        # 分类整理提取项
        constraints = []
        decisions = []
        facts = []
        pending = []

        for item in extracted_items:
            if not item.still_valid:
                continue
            if item.priority == Priority.CONSTRAINT:
                constraints.append(item.content)
            elif item.priority == Priority.DECISION:
                decisions.append(item.content)
            elif item.priority == Priority.FACT:
                facts.append(item.content)
            elif item.priority == Priority.TODO:
                pending.append(item.content)

        # 保留最近 N 轮原始对话
        recent = conversation[-(self.max_recent_turns * 2):]

        # 生成摘要
        summary_parts = []
        if constraints:
            summary_parts.append(f"Active constraints: {'; '.join(constraints)}")
        if decisions:
            summary_parts.append(f"Decisions: {'; '.join(decisions)}")
        if pending:
            summary_parts.append(f"Pending: {'; '.join(pending)}")
        state_summary = ". ".join(summary_parts) if summary_parts else "No significant state."

        self._last_extracted_items = extracted_items

        return CompressedContext(
            state_summary=state_summary,
            constraints=constraints,
            decisions=decisions,
            key_facts=facts,
            pending_items=pending,
            recent_turns=recent,
            compression_metadata={
                "original_turns": len(conversation) // 2,
                "retained_turns": len(recent) // 2,
                "extracted_items": len(extracted_items),
                "compression_ratio": f"{len(conversation) // 2}:{len(recent) // 2}",
            },
        )

    @staticmethod
    def _format_conversation(conversation: list[dict]) -> str:
        """将对话历史格式化为可读文本"""
        lines = []
        turn = 0
        for msg in conversation:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "system":
                lines.append(f"[System]: {content}")
            else:
                turn += 1
                lines.append(f"[Turn {turn}] {role.capitalize()}: {content}")
        return "\n\n".join(lines)


# ============================================================
# 便捷函数
# ============================================================

def estimate_tokens(conversation: list[dict]) -> int:
    """
    粗略估计对话的 token 数。

    使用简单规则：英文 ~1.3 tokens/word，中文 ~1.5 tokens/char
    这里使用保守估计 ~4 chars/token（混合中英文）。
    """
    total_chars = sum(
        len(msg.get("content", "")) for msg in conversation
    )
    return total_chars // 4


def detect_drift_indicators(
    current_response: str,
    previous_responses: list[str],
) -> dict:
    """
    从当前响应和历史响应中检测漂移指标。

    简易版实现，生产环境建议使用嵌入相似度或专用分类器。

    Returns:
        dict with keys:
        - repetition_rate: 与历史回复的重复度
        - off_topic_score: 离题评分
        - inconsistency_score: 前后不一致评分
    """
    if not previous_responses:
        return {"repetition_rate": 0.0, "off_topic_score": 0.0, "inconsistency_score": 0.0}

    # 简单的词级重复检测
    current_words = set(current_response.lower().split())
    repetition_scores = []
    for prev in previous_responses[-5:]:  # 只比较最近5轮
        prev_words = set(prev.lower().split())
        if prev_words:
            overlap = len(current_words & prev_words) / len(prev_words)
            repetition_scores.append(overlap)

    repetition_rate = sum(repetition_scores) / len(repetition_scores) if repetition_scores else 0.0

    return {
        "repetition_rate": round(repetition_rate, 3),
        "off_topic_score": 0.0,    # 需要外部分类器
        "inconsistency_score": 0.0, # 需要外部分类器
    }


# ============================================================
# 演示
# ============================================================

if __name__ == "__main__":
    # 模拟一段对话历史
    demo_conversation = [
        {"role": "system", "content": "You are a financial analyst assistant."},
        {"role": "user", "content": "帮我分析 Apple 的 Q2 财报"},
        {"role": "assistant", "content": "好的，Apple Q2 财报显示营收增长 5%..."},
        {"role": "user", "content": "重点关注毛利率趋势"},
        {"role": "assistant", "content": "毛利率方面，Q2 为 46.3%，同比增长 0.7 个百分点..."},
        {"role": "user", "content": "和微软对比一下"},
        {"role": "assistant", "content": "对比微软：Apple 毛利率 46.3% vs 微软 69.8%..."},
        # ... 实际场景中会有更多轮
    ]

    extractor = MemoryExtractor(max_recent_turns=3)

    # 检查是否需要压缩
    tokens = estimate_tokens(demo_conversation)
    should = extractor.should_compress(
        turn_count=len(demo_conversation) // 2,
        estimated_tokens=tokens,
    )
    print(f"Tokens: {tokens}, Should compress: {should}")

    # 构建提取请求（实际 LLM 调用由上层完成）
    extraction_data = extractor.extract(demo_conversation)
    print(f"\nExtraction prompt preview:\n{extraction_data['prompt'][:200]}...")

    # 模拟 LLM 返回的解析结果
    mock_items = [
        ExtractedItem(Priority.CONSTRAINT, "关注毛利率趋势", [2], True),
        ExtractedItem(Priority.CONSTRAINT, "与微软对比分析", [3], True),
        ExtractedItem(Priority.FACT, "Apple Q2 毛利率 46.3%", [1, 2], True),
        ExtractedItem(Priority.FACT, "微软毛利率 69.8%", [3], True),
        ExtractedItem(Priority.DECISION, "需要进一步分析运营利润率", [3], True),
        ExtractedItem(Priority.TODO, "提供投资建议", [3], True),
    ]

    compressed = extractor.compress(demo_conversation, mock_items)
    print(f"\n=== Compressed Context ===\n{compressed.format_for_llm()}")
