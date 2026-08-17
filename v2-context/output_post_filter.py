"""
输出后处理过滤器 — Anthropic Claude 的 logit_bias 替代方案

Claude API 不支持 logit_bias，无法在 token 采样阶段精确压制特定词汇。
本模块提供轻量级的输出后处理：在 Claude 生成文本后，检测和清理漂移特征。

使用方式：
    from output_post_filter import PostFilter
    pf = PostFilter()
    cleaned_text, issues = pf.filter(claude_response_text)

为什么需要这个：
    OpenAI 的 logit_bias 在采样阶段阻止跑题 token 的生成。
    Claude 没有这个能力，只能在生成后检测 → 过滤 → 必要时触发重试。
    这是"事后补救"而非"事前预防"，效果弱于 logit_bias，但聊胜于无。
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class IssueType(Enum):
    """检测到的问题类型"""
    TOPIC_SHIFT = "topic_shift"        # 🏃 跑题转折
    REDUNDANT_SELF_REF = "self_ref"    # 🤖 冗余自述
    OVER_APOLOGIZING = "apology"       # 🙇 过度道歉
    GHOST_TURN = "ghost_turn"          # 👻 幻想对话回合
    FORMAT_COLLAPSE = "format"         # 🎛️ 格式崩坏
    REPETITION = "repetition"          # 🌀 重复内容


@dataclass
class FilterIssue:
    """单个过滤发现"""
    issue_type: IssueType
    matched_text: str
    position: int  # 在原文中的位置
    severity: str  # "low" | "medium" | "high"
    suggestion: str


@dataclass
class FilterResult:
    """过滤结果"""
    original: str
    cleaned: str
    issues: list[FilterIssue] = field(default_factory=list)
    was_modified: bool = False

    @property
    def needs_retry(self) -> bool:
        """是否需要丢弃当前回复并重试"""
        return any(i.severity == "high" for i in self.issues)


class PostFilter:
    """
    Claude 输出后处理过滤器。

    检测模式分为两类：
    - low/medium severity：静默清理，移除问题片段
    - high severity：标记需要重试（当前回复已严重偏离，不应保留）
    """

    # ================================================================
    # 检测规则 — 每条标注针对的症状
    # ================================================================

    # 🏃 跑题转折词 — 模型常用这些短语切换话题
    TOPIC_SHIFT_PATTERNS = [
        (re.compile(r'\bAnyway,?\s', re.IGNORECASE), "high",
         "检测到话题转折词 'Anyway'，可能正在切换话题"),
        (re.compile(r'\bBy the way,?\s', re.IGNORECASE), "medium",
         "检测到旁支插入 'By the way'，可能分散注意力"),
        (re.compile(r'\bSpeaking of which,?\s', re.IGNORECASE), "medium",
         "检测到联想跳跃 'Speaking of which'"),
        (re.compile(r'\bThat said,?\s', re.IGNORECASE), "low",
         "检测到让步转折 'That said'，轻微偏离风险"),
        (re.compile(r'话说回来[,，]?\s*'), "medium",
         "中文跑题转折词"),
        (re.compile(r'顺带一提[,，]?\s*'), "medium",
         "中文旁支插入"),
    ]

    # 🤖 冗余自述 — 模型自报家门，纯浪费 token
    SELF_REF_PATTERNS = [
        (re.compile(
            r'\bAs an AI( language model)?( (assistant|developed|created|trained) by [^,.!?\n]+)?[,.]?\s*',
            re.IGNORECASE
        ), "low",
         "冗余自述 'As an AI...'，对任务无贡献"),
        (re.compile(
            r'\bI am an AI( language model)?( (assistant|developed|created) by [^,.!?\n]+)?[,.]?\s*',
            re.IGNORECASE
        ), "low",
         "冗余自述 'I am an AI...'"),
        (re.compile(r'作为(一个|一名)?AI(助手|语言模型)?[,，]?\s*'), "low",
         "中文冗余自述"),
    ]

    # 🙇 过度道歉 — 跑题后常以道歉开头，浪费时间且不解决问题
    APOLOGY_PATTERNS = [
        (re.compile(
            r'\bI apologize for (the|any) (confusion|misunderstanding|mistake|error|oversight)',
            re.IGNORECASE
        ), "low",
         "过度道歉，建议直接纠正而非道歉"),
        (re.compile(
            r'\bI(\'m| am) sorry (for|about|that|if)',
            re.IGNORECASE
        ), "low",
         "过度道歉"),
        (re.compile(r'抱歉[,，]?(我|刚才|之前)?(的)?(误解|错误|疏忽|混淆)'), "low",
         "中文过度道歉"),
    ]

    # 👻 幻想对话回合 — Claude 有时会编造 Human:/Assistant: 前缀
    GHOST_TURN_PATTERNS = [
        (re.compile(r'\n\nHuman:\s*.+', re.IGNORECASE), "high",
         "👻 模型幻想了新的用户消息！这是严重的 self-play 幻觉"),
        (re.compile(r'\n\nAssistant:\s*.+', re.IGNORECASE), "high",
         "👻 模型幻想了自己的后续回复！"),
        (re.compile(r'\n\nUser:\s*.+', re.IGNORECASE), "high",
         "👻 模型幻想了新的用户消息 (User:)"),
    ]

    # 🎛️ 格式崩坏 — 检测输出结构是否散架
    FORMAT_PATTERNS = [
        (re.compile(r'\n{4,}'), "low",
         "连续 4+ 空行，格式可能崩坏"),
    ]

    def __init__(self, custom_patterns: list[tuple[re.Pattern, str, str]] | None = None):
        """
        Args:
            custom_patterns: 可选的自定义检测规则
                            格式: [(compiled_regex, severity, description), ...]
        """
        self._rules: list[tuple[re.Pattern, str, str, IssueType]] = []
        self._register_rules()
        if custom_patterns:
            for pat, sev, desc in custom_patterns:
                self._rules.append((pat, sev, desc, IssueType.TOPIC_SHIFT))

    def _register_rules(self) -> None:
        """注册所有检测规则"""
        for pat, sev, desc in self.TOPIC_SHIFT_PATTERNS:
            self._rules.append((pat, sev, desc, IssueType.TOPIC_SHIFT))
        for pat, sev, desc in self.SELF_REF_PATTERNS:
            self._rules.append((pat, sev, desc, IssueType.REDUNDANT_SELF_REF))
        for pat, sev, desc in self.APOLOGY_PATTERNS:
            self._rules.append((pat, sev, desc, IssueType.OVER_APOLOGIZING))
        for pat, sev, desc in self.GHOST_TURN_PATTERNS:
            self._rules.append((pat, sev, desc, IssueType.GHOST_TURN))
        for pat, sev, desc in self.FORMAT_PATTERNS:
            self._rules.append((pat, sev, desc, IssueType.FORMAT_COLLAPSE))

    def filter(self, text: str) -> FilterResult:
        """
        对 Claude 输出做后处理过滤。

        Args:
            text: Claude 的原始输出文本

        Returns:
            FilterResult，包含清理后文本和检测到的问题列表
        """
        issues: list[FilterIssue] = []
        cleaned = text

        for pattern, severity, description, issue_type in self._rules:
            for match in pattern.finditer(cleaned):
                issues.append(FilterIssue(
                    issue_type=issue_type,
                    matched_text=match.group().strip(),
                    position=match.start(),
                    severity=severity,
                    suggestion=description,
                ))

        # 按位置排序（从后往前处理，避免索引偏移）
        issues.sort(key=lambda i: i.position, reverse=True)

        # 清理 high severity 的问题片段（截断）
        high_issues = [i for i in issues if i.severity == "high"]
        if high_issues:
            # 找到第一个 high severity 问题的位置，从那里截断
            first_high_pos = min(i.position for i in high_issues)
            cleaned = cleaned[:first_high_pos].rstrip()
            # 只保留 high 之前的 low/medium issues
            issues = [i for i in issues if i.position < first_high_pos] + high_issues

        # 清理 low/medium severity 的问题片段
        for issue in issues:
            if issue.severity in ("low", "medium"):
                cleaned = self._remove_pattern(cleaned, issue.matched_text)

        return FilterResult(
            original=text,
            cleaned=cleaned.strip(),
            issues=issues,
            was_modified=len(issues) > 0,
        )

    @staticmethod
    def _remove_pattern(text: str, pattern_text: str) -> str:
        """安全地移除匹配文本（精确匹配一次）"""
        return text.replace(pattern_text, "", 1)

    def quick_scan(self, text: str) -> bool:
        """
        快速扫描：是否包含任何漂移特征？

        Returns:
            True 表示存在问题，建议做完整过滤
        """
        for pattern, _, _, _ in self._rules:
            if pattern.search(text):
                return True
        return False


# ============================================================
# 便捷函数
# ============================================================

def create_default_filter() -> PostFilter:
    """创建默认配置的过滤器"""
    return PostFilter()


# ============================================================
# 演示
# ============================================================

if __name__ == "__main__":
    pf = PostFilter()

    # 模拟 Claude 的跑题输出
    test_cases = [
        # 案例 1：🏃 跑题转折 + 🤖 冗余自述
        (
            "🏃 跑题 + 🤖 自述",
            "The revenue growth was 5% quarter over quarter. "
            "Anyway, as an AI assistant developed by Anthropic, I should note that "
            "revenue metrics can vary by accounting method."
        ),
        # 案例 2：👻 幻想对话回合
        (
            "👻 幻想对话",
            "The analysis is complete. The key metrics are as follows.\n\n"
            "Human: Can you also check the profit margins?\n\n"
            "Assistant: Of course, let me look at the profit margins..."
        ),
        # 案例 3：🙇 过度道歉
        (
            "🙇 过度道歉",
            "I apologize for the confusion. I'm sorry if my previous response "
            "was unclear. The correct answer is that the 403 error was caused by "
            "missing Data Export permissions."
        ),
        # 案例 4：正常回复（应无过滤）
        (
            "✅ 正常回复",
            "The Q2 revenue was $94.8B, up 5% YoY. Gross margin improved "
            "to 46.3% from 45.6% in the prior year. Key drivers include "
            "Services growth and favorable product mix."
        ),
    ]

    for label, text in test_cases:
        result = pf.filter(text)
        print(f"\n{'='*60}")
        print(f"案例: {label}")
        print(f"需要重试: {result.needs_retry}")
        if result.issues:
            for issue in result.issues:
                print(f"  [{issue.severity.upper():6s}] {issue.issue_type.value:20s} | {issue.suggestion}")
            print(f"\n原文 ({len(result.original)} chars):")
            print(f"  {result.original[:120]}...")
            print(f"\n清理后 ({len(result.cleaned)} chars):")
            print(f"  {result.cleaned[:120]}...")
        else:
            print(f"  ✅ 未检测到问题，输出清洁")
