"""
LangGraph State Machine — Attention Drift Control via Behavioral Gating

核心思想：
    不承诺消除漂移。只做一件事——把模型的发散半径限制在单个状态内部。
    每个状态定义 ALLOWED（允许行为）和 FORBIDDEN（禁止行为），
    每次 LLM 调用前根据当前状态注入专属 prompt。

依赖：
    pip install langgraph langchain-core langchain-openai
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Optional, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages


# ============================================================
# 状态定义
# ============================================================

class ConversationState(Enum):
    """对话状态枚举"""
    INIT = "init"
    CLARIFY = "clarify"
    RESEARCH = "research"       # 分析探索 —— 替代旧版的通用 TASKING
    DECISION = "decision"       # 判断输出
    VERIFYING = "verifying"
    COMPLETED = "completed"
    DRIFT_RECOVERY = "drift_recovery"


# ============================================================
# 每个状态的 ALLOWED / FORBIDDEN prompt
# ============================================================
# 这些 prompt 在每次 LLM 调用前注入到 system prompt 中。
# 它们不阻止漂移——但把漂移的"允许半径"限制在了当前状态内。

STATE_PROMPTS: dict[str, str] = {
    ConversationState.INIT.value: """
## 当前状态：INIT（任务解析阶段）
### 允许的行为
- 解析用户消息，提取任务描述和约束条件
- 识别任务类型（分析型 / 决策型 / 探索型）
- 确认不明确的地方
### 禁止的行为
- 直接执行任务（还没搞清楚要做什么）
- 猜测用户没说过的需求
- 给出建议或结论
### 状态边界
如果你已经理解了用户的任务和约束，在回复末尾声明：
"[STATE_TRANSITION: CLARIFY] 或 [STATE_TRANSITION: RESEARCH]"
""",

    ConversationState.CLARIFY.value: """
## 当前状态：CLARIFY（需求澄清阶段）
### 允许的行为
- 提出 1-3 个精准的澄清问题
- 确认对用户需求的理解是否正确
- 列出你已理解的部分和仍不确定的部分
### 禁止的行为
- 猜测答案来填补信息缺口
- 在不明确的情况下开始分析
- 一次问太多问题（>3个）
### 状态边界
当你确认信息足够时，声明：
"[STATE_TRANSITION: RESEARCH]"
""",

    ConversationState.RESEARCH.value: """
## 当前状态：RESEARCH（分析探索阶段）
### 允许的行为
- 分析数据、事实、趋势
- 提出假设并尝试验证
- 列出多种可能性和解释
- 引用来源和证据
- 请求更多信息以深化分析
### 禁止的行为
- 给出确定性建议或结论
- 安慰用户、表达无关的同情（不属于分析任务）
- 哲学扩展、抽象升华
- 猜测用户意图而不先确认
- 切换到不相关的知识领域
### 状态边界
如果用户明确要求建议或选择，不要在当前状态下给出。
回复："这需要进入决策阶段。要我现在切换到 DECISION 模式吗？"
或声明："[STATE_TRANSITION: DECISION]"
""",

    ConversationState.DECISION.value: """
## 当前状态：DECISION（决策输出阶段）
### 允许的行为
- 基于已分析的事实给出具体建议
- 对多个选项排序并说明理由
- 做风险分析和 trade-off 对比
- 指出建议的边界条件和假设前提
### 禁止的行为
- 重新开始大规模分析（这是 RESEARCH 的事）
- 引入全新的理论框架
- 回避决策——"这取决于很多因素"是不够的
- 推翻之前已确认的事实而不标注变更
### 状态边界
如果用户要求重新分析或提出全新的分析角度，声明：
"[STATE_TRANSITION: RESEARCH]"
如果所有建议已给出，声明：
"[STATE_TRANSITION: VERIFYING]"
""",

    ConversationState.VERIFYING.value: """
## 当前状态：VERIFYING（自检验收阶段）
### 允许的行为
- 逐项核对任务是否完成
- 检查所有约束是否被遵守
- 补充遗漏的信息
- 标记未解决的问题
### 禁止的行为
- 引入新的分析任务
- 重新讨论已做出的决策
- 忽视检查中发现的问题
### 状态边界
全部通过 → "[STATE_TRANSITION: COMPLETED]"
发现问题 → 回到 RESEARCH 或 DECISION
""",

    ConversationState.COMPLETED.value: """
## 当前状态：COMPLETED（交付阶段）
### 允许的行为
- 生成最终的结构化总结
- 列出已完成和未完成的事项
- 标记对话统计信息
### 禁止的行为
- 继续对话（任务已完成）
- 引入新话题
""",

    ConversationState.DRIFT_RECOVERY.value: """
## 当前状态：DRIFT_RECOVERY（漂移恢复阶段）
### 允许的行为
- 明确声明检测到偏离
- 重新聚焦到核心任务
- 回顾上一个稳定状态的关键信息
### 禁止的行为
- 继续之前的偏离方向
- 装作无事发生
- 不声明恢复就直接继续任务
### 状态边界
恢复完成 → "[STATE_TRANSITION: RESEARCH]" 或回到被中断的状态
""",
}


# ============================================================
# 状态转移触发词（规则层兜底，绕过模型自判延迟）
# ============================================================

FORCED_TRANSITION_TRIGGERS: dict[str, list[str]] = {
    ConversationState.RESEARCH.value: [
        "分析", "看看数据", "对比", "趋势", "为什么", "原因",
        "explore", "analyze", "investigate", "research", "look into",
    ],
    ConversationState.DECISION.value: [
        "建议", "推荐", "选哪个", "怎么选", "给个方案", "决定",
        "recommend", "decide", "choose", "which one", "suggest",
    ],
    ConversationState.CLARIFY.value: [
        "什么意思", "没听懂", "再说一遍", "不清楚",
        "what do you mean", "clarify", "explain that",
    ],
}


# ============================================================
# 图状态（LangGraph State Schema）
# ============================================================

class GraphState(TypedDict):
    messages: Annotated[list, add_messages]
    conversation_state: str
    core_task: str
    constraints: list[str]
    key_facts: list[str]
    completed_tasks: list[str]
    pending_tasks: list[str]
    drift_score: float
    consecutive_drift_turns: int
    user_correction_count: int
    last_stable_checkpoint: Optional[str]
    turn_count: int


# ============================================================
# 核心：每次 LLM 调用前注入状态专属 prompt
# ============================================================

def build_system_prompt_for_turn(
    state: str,
    base_system_prompt: str,
    core_task: str,
    constraints: list[str],
    key_facts: list[str],
) -> str:
    """
    根据当前状态拼接 system prompt。

    这是 v3 和 v1 的关键区别：
    v1 = 固定 system prompt（第一轮到第一百轮都一样）
    v3 = 每次调用前动态注入状态约束
    """
    state_prompt = STATE_PROMPTS.get(state, "")

    parts = [base_system_prompt]

    if core_task:
        parts.append(f"\n## 核心任务\n{core_task}")

    if constraints:
        parts.append("\n## 活跃约束")
        for c in constraints:
            parts.append(f"- {c}")

    if key_facts:
        parts.append("\n## 已确立的事实")
        for f in key_facts:
            parts.append(f"- {f}")

    parts.append(state_prompt)

    return "\n".join(parts)


# ============================================================
# 状态转移检测
# ============================================================

def detect_state_transition_request(
    response_text: str,
    current_state: str,
    user_message: str,
) -> Optional[str]:
    """
    检测是否需要切换状态。

    两个来源：
    1. 模型主动声明 [STATE_TRANSITION: TARGET]
    2. 用户消息触发强制切换规则
    """
    # 来源 1：模型主动声明
    import re
    match = re.search(r'\[STATE_TRANSITION:\s*(\w+)\]', response_text)
    if match:
        target = match.group(1).upper()
        # 映射到枚举值
        for state in ConversationState:
            if state.value == target.lower():
                return state.value
        return None

    # 来源 2：规则强制切换（用户消息触发）
    for target_state, keywords in FORCED_TRANSITION_TRIGGERS.items():
        if target_state == current_state:
            continue  # 已经在目标状态
        user_lower = user_message.lower()
        if any(kw in user_lower for kw in keywords):
            return target_state

    return None


# ============================================================
# 漂移检测
# ============================================================

DRIFT_THRESHOLDS = {
    "off_topic_score": 0.7,
    "constraint_violation": 3,
    "no_progress_turns": 4,
    "user_correction": 3,
    "max_consecutive_drift": 2,
}


def detect_drift(state: GraphState) -> dict:
    """
    检测漂移。

    注意：v3 的漂移检测比 v2 更宽松——
    因为有状态约束，模型在状态内的"发散"是允许的。
    只有明显违反 FORBIDDEN 列表或连续无进展才触发恢复。
    """
    reasons = []
    score = 0.0

    if state.get("consecutive_drift_turns", 0) > 0:
        score += 0.3 * state["consecutive_drift_turns"]
        reasons.append(f"连续 {state['consecutive_drift_turns']} 轮漂移")

    if state.get("user_correction_count", 0) >= DRIFT_THRESHOLDS["user_correction"]:
        score += 0.5
        reasons.append(f"用户纠正 {state['user_correction_count']} 次")

    # v3 特有的检测：是否违反了当前状态的 FORBIDDEN 列表
    # 实际实现需要对 LLM 输出做分类判断

    return {
        "is_drifting": score >= 0.5,
        "score": min(score, 1.0),
        "reasons": reasons,
    }


# ============================================================
# 节点函数
# ============================================================

def node_init(state: GraphState, llm) -> GraphState:
    """INIT：解析任务，提取约束，决定下一个状态"""
    system_msg = next(
        (m for m in state["messages"] if getattr(m, "type", None) == "system"),
        None
    )
    if system_msg:
        # 生产环境：用 LLM 解析 system prompt
        state["core_task"] = "回答用户问题并保持准确"
        state["constraints"] = ["保持一致性", "不知道就说不知道"]

    state["conversation_state"] = ConversationState.CLARIFY.value
    state["last_stable_checkpoint"] = ConversationState.INIT.value
    return state


def node_clarify(state: GraphState, llm) -> GraphState:
    """CLARIFY：追问澄清，直到信息足够进入 RESEARCH"""
    # 检查是否已经从用户消息中获得了足够信息
    enough_info = state.get("core_task") and len(state["core_task"]) >= 10
    if enough_info:
        state["conversation_state"] = ConversationState.RESEARCH.value
        state["last_stable_checkpoint"] = ConversationState.CLARIFY.value
    return state


def node_research(state: GraphState, llm) -> GraphState:
    """RESEARCH：分析探索 —— v3 最核心的状态"""
    state["turn_count"] += 1

    # 检查状态转移（用户消息触发）
    user_msg = state["messages"][-1].content if state["messages"] else ""
    forced = detect_state_transition_request("", state["conversation_state"], user_msg)
    if forced and forced != state["conversation_state"]:
        state["conversation_state"] = forced
        return state

    # 漂移检测
    drift = detect_drift(state)
    state["drift_score"] = drift["score"]
    if drift["is_drifting"]:
        state["consecutive_drift_turns"] += 1
        if state["consecutive_drift_turns"] >= DRIFT_THRESHOLDS["max_consecutive_drift"]:
            state["conversation_state"] = ConversationState.DRIFT_RECOVERY.value
    else:
        state["consecutive_drift_turns"] = 0

    return state


def node_decision(state: GraphState, llm) -> GraphState:
    """DECISION：判断输出 —— 只做建议和排序，不做新分析"""
    state["turn_count"] += 1

    user_msg = state["messages"][-1].content if state["messages"] else ""
    forced = detect_state_transition_request("", state["conversation_state"], user_msg)
    if forced and forced != state["conversation_state"]:
        state["conversation_state"] = forced
        return state

    # 如果用户要求重新分析
    reanalysis_keywords = ["重新分析", "再看看数据", "re-analyze", "look at the data again"]
    if any(kw in user_msg.lower() for kw in reanalysis_keywords):
        state["conversation_state"] = ConversationState.RESEARCH.value
        return state

    return state


def node_verify(state: GraphState, llm) -> GraphState:
    """VERIFYING：逐项核对，发现遗漏回到 RESEARCH"""
    if not state.get("pending_tasks"):
        state["conversation_state"] = ConversationState.COMPLETED.value
    else:
        # 有遗漏 → 回到 RESEARCH 补充
        state["conversation_state"] = ConversationState.RESEARCH.value
    return state


def node_drift_recovery(state: GraphState, llm) -> GraphState:
    """DRIFT_RECOVERY：承认偏离，回退焦点"""
    state["consecutive_drift_turns"] = 0
    state["drift_score"] = 0.0
    # 回退到上一个稳定状态（通常是 RESEARCH）
    state["conversation_state"] = ConversationState.RESEARCH.value
    return state


def node_complete(state: GraphState, llm) -> GraphState:
    """COMPLETED：交付总结"""
    return state


# ============================================================
# 路由
# ============================================================

ROUTER_MAP = {
    ConversationState.INIT.value: "node_init",
    ConversationState.CLARIFY.value: "node_clarify",
    ConversationState.RESEARCH.value: "node_research",
    ConversationState.DECISION.value: "node_decision",
    ConversationState.VERIFYING.value: "node_verify",
    ConversationState.DRIFT_RECOVERY.value: "node_drift_recovery",
    ConversationState.COMPLETED.value: "node_complete",
}


def router(state: GraphState) -> str:
    return ROUTER_MAP.get(state["conversation_state"], "node_research")


def should_continue(state: GraphState) -> str:
    if state["conversation_state"] == ConversationState.COMPLETED.value:
        return END
    return "continue"


# ============================================================
# 构建图
# ============================================================

def build_drift_control_graph(llm=None) -> StateGraph:
    workflow = StateGraph(GraphState)

    workflow.add_node("node_init", lambda s: node_init(s, llm))
    workflow.add_node("node_clarify", lambda s: node_clarify(s, llm))
    workflow.add_node("node_research", lambda s: node_research(s, llm))
    workflow.add_node("node_decision", lambda s: node_decision(s, llm))
    workflow.add_node("node_verify", lambda s: node_verify(s, llm))
    workflow.add_node("node_drift_recovery", lambda s: node_drift_recovery(s, llm))
    workflow.add_node("node_complete", lambda s: node_complete(s, llm))

    workflow.set_entry_point("node_init")

    for node in ROUTER_MAP.values():
        if node != "node_complete":
            workflow.add_conditional_edges(node, should_continue, {
                "continue": node, END: END,
            })

    workflow.add_edge("node_complete", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


# ============================================================
# 便捷封装
# ============================================================

class DriftControlGraph:
    """漂移控制状态机封装"""

    def __init__(self, llm=None):
        self.llm = llm
        self.graph = build_drift_control_graph(llm)

    def invoke(
        self,
        user_input: str,
        thread_id: str = "default",
        system_prompt: str | None = None,
    ) -> dict:
        from langchain_core.messages import SystemMessage, HumanMessage

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=user_input))

        config = {"configurable": {"thread_id": thread_id}}
        return self.graph.invoke({
            "messages": messages,
            "conversation_state": ConversationState.INIT.value,
            "core_task": "",
            "constraints": [],
            "key_facts": [],
            "completed_tasks": [],
            "pending_tasks": [],
            "drift_score": 0.0,
            "consecutive_drift_turns": 0,
            "user_correction_count": 0,
            "last_stable_checkpoint": None,
            "turn_count": 0,
        }, config)

    def resume(self, thread_id: str) -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        state = self.graph.get_state(config)
        if state:
            return self.graph.invoke(None, config)
        raise ValueError(f"No checkpoint found for thread: {thread_id}")


# ============================================================
# 演示：展示 STATE_PROMPTS 注入效果
# ============================================================

if __name__ == "__main__":
    # 演示：不同状态下注入的 prompt 差异
    base = "你是高可靠性助手。核心任务是帮助用户分析技术问题。"

    for state in [ConversationState.RESEARCH, ConversationState.DECISION]:
        prompt = build_system_prompt_for_turn(
            state=state.value,
            base_system_prompt=base,
            core_task="分析 Apple Q2 财报并给出投资建议",
            constraints=["始终提供数据来源", "不确定时标注"],
            key_facts=["Apple Q2 毛利率 46.3%", "营收同比增长 5%"],
        )
        print(f"\n{'='*60}")
        print(f"State: {state.value}")
        print(f"Prompt length: {len(prompt)} chars")
        print(f"\n--- Last 300 chars ---")
        print(prompt[-300:])
