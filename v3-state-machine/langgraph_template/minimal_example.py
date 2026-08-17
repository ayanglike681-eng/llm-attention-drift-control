"""
L3 State Machine — 最简可跑示例（5 分钟跑通）

3 个状态：RESEARCH → DECISION → DONE
硬编码所有配置。先跑通，再看完整模板（advanced/）。

依赖：pip install langgraph langchain-openai
运行：export OPENAI_API_KEY=sk-... && python minimal_example.py
"""

from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI


# ============================================================
# 三个状态的 prompt（硬编码，不改）
# ============================================================

RESEARCH_PROMPT = """
## 当前状态：调查分析
允许：收集信息、分析数据、提出假设
禁止：给出建议、做决定、闲聊
如果用户要建议 → 回复 "需要切换到决策模式。要切换吗？"
"""

DECISION_PROMPT = """
## 当前状态：决策输出
允许：排序选项、风险分析、给出建议
禁止：收集新信息、重新分析、回避决定
"""


# ============================================================
# 状态图（最简版，3 状态，无 drift recovery）
# ============================================================

class State(TypedDict):
    messages: Annotated[list, add_messages]
    stage: str  # "research" | "decision" | "done"


def node_research(state: State, llm) -> State:
    """调查阶段"""
    system_msg = state["messages"][0].content if state["messages"] else ""
    full_prompt = f"{system_msg}\n\n{RESEARCH_PROMPT}"
    # 重建 messages（替换 system prompt）
    messages = [{"role": "system", "content": full_prompt}]
    messages.extend(state["messages"][1:])  # 历史对话
    response = llm.invoke(messages)
    state["messages"].append(response)
    # 检查是否请求切换
    if "切换到决策" in response.content or "需要切换" in response.content:
        state["stage"] = "decision"
    return state


def node_decision(state: State, llm) -> State:
    """决策阶段"""
    system_msg = state["messages"][0].content if state["messages"] else ""
    full_prompt = f"{system_msg}\n\n{DECISION_PROMPT}"
    messages = [{"role": "system", "content": full_prompt}]
    messages.extend(state["messages"][1:])
    response = llm.invoke(messages)
    state["messages"].append(response)
    if "完成" in response.content or "总结" in response.content:
        state["stage"] = "done"
    return state


def node_done(state: State, llm) -> State:
    """结束"""
    print(f"\n✅ 对话完成。共 {len(state['messages']) // 2} 轮。")
    return state


def router(state: State) -> str:
    return {"research": "node_research", "decision": "node_decision", "done": "node_done"}[state["stage"]]


def should_continue(state: State) -> str:
    return END if state["stage"] == "done" else "continue"


# ============================================================
# 构建
# ============================================================

def build():
    w = StateGraph(State)
    w.add_node("node_research", lambda s: node_research(s, llm))
    w.add_node("node_decision", lambda s: node_decision(s, llm))
    w.add_node("node_done", lambda s: node_done(s, llm))
    w.set_entry_point("node_research")
    for n in ["node_research", "node_decision"]:
        w.add_conditional_edges(n, should_continue, {"continue": n, END: END})
    w.add_edge("node_done", END)
    return w.compile(checkpointer=MemorySaver())


# ============================================================
# 跑
# ============================================================

if __name__ == "__main__":
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ 请先设置: export OPENAI_API_KEY='sk-...'")
        exit(1)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    app = build()

    print("L3 最简状态机已启动（research → decision → done）")
    print("输入 'q' 退出\n")

    config = {"configurable": {"thread_id": "demo"}}
    system_prompt = "你是技术助手。分析用户问题，必要时给出建议。"

    from langchain_core.messages import HumanMessage, SystemMessage

    while True:
        user_input = input("👤 You: ")
        if user_input.lower() == "q":
            break
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_input)]
        result = app.invoke({"messages": messages, "stage": "research"}, config)
        last_msg = result["messages"][-1]
        print(f"\n🤖 [{result['stage']}]: {last_msg.content[:500]}\n")
