"""
Anthropic Claude API — Attention Drift Control via Stop Sequences

Claude API 不支持 frequency_penalty / presence_penalty / logit_bias。
替代策略：
1. stop_sequences — 紧急截断跑题输出（本文件）
2. output_post_filter.py — 输出后处理过滤（logit_bias 的替代）
3. System prompt 模拟 penalty 效果（参见 v1-prompt/）
4. 动态 temperature — 随轮次降低

依赖：pip install anthropic
"""

import anthropic

client = anthropic.Anthropic(api_key="YOUR_API_KEY")

# ============================================================
# System Prompt（与 v1 联动——要求模型自我检测漂移）
# ============================================================

DRIFT_CONTROL_SYSTEM_PROMPT = """You are a high-reliability assistant.

Core task: {TASK_DESCRIPTION}

Drift prevention rules:
1. Before every response, verify you still understand the core task
2. If you detect topic drift, output [DRIFT_DETECTED] immediately and stop
3. Every 5 turns, start with: [STATUS: Turn N | On-Task: YES/NO]
4. Do NOT generate text after [DRIFT_DETECTED] — the API will cut you off there
"""

# ============================================================
# Stop Sequences — 每个标注了针对的症状
# ============================================================

STOP_SEQUENCES = [
    # 🏃 跑题狂奔 — 模型自我检测到偏离时主动标记，API 立即截断
    # 需要配合 system prompt 中的规则 "If you detect topic drift, output [DRIFT_DETECTED]"
    "[DRIFT_DETECTED]",

    # 👻 幻想额外对话 — Claude 在长对话中有时会编造后续的 Human/Assistant 回合
    # 这是 Claude 系模型的已知行为（self-play hallucination）
    "\n\nHuman:",
    "\n\nAssistant:",

    # 🏃 跑题狂奔 — 通用截断标记，用于紧急刹车
    "---",

    # 🏃 跑题狂奔 — 显式结束标记，防止模型在任务完成后继续生成无关内容
    "END_OF_CONVERSATION",

    # 🏃 跑题狂奔 — 备用跑题标记
    "[OFF_TOPIC]",
]


# ============================================================
# 核心函数：带漂移控制的 Claude API 调用
# ============================================================

def create_drift_resistant_message(
    user_message: str,
    conversation_history: list[dict] | None = None,
    turn_number: int = 1,
    task_description: str = "Answer questions accurately and stay on topic.",
    temperature: float = 0.3,
    max_tokens: int = 2048,
    model: str = "claude-sonnet-4-6",
) -> anthropic.types.Message:
    """
    发送带有漂移控制的消息。

    Args:
        user_message: 当前用户消息
        conversation_history: 之前的对话历史 [{"role": "...", "content": "..."}]
        turn_number: 当前对话轮次（用于周期性状态检查和动态 temperature）
        task_description: 核心任务描述
        temperature: 温度参数 (0.0-1.0)，越低越稳定
        max_tokens: 最大输出 token 数
        model: 模型 ID

    Returns:
        Claude API 响应对象
    """
    system_prompt = DRIFT_CONTROL_SYSTEM_PROMPT.format(
        TASK_DESCRIPTION=task_description
    )

    messages = []
    if conversation_history:
        messages.extend(conversation_history)

    # 每5轮注入状态检查锚点
    # 对应 v1 的"周期性状态声明"策略
    if turn_number % 5 == 0:
        user_message = (
            f"[状态检查 — 第 {turn_number} 轮]\n"
            f"请在回复前确认：你仍记得核心任务吗？上一轮是否偏离？\n\n"
            f"{user_message}"
        )

    messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        stop_sequences=STOP_SEQUENCES,
        messages=messages,
    )

    # 分析停止原因
    if response.stop_reason == "stop_sequence":
        matched_seq = response.stop_sequence
        _handle_stop(matched_seq, turn_number)

    return response


def _handle_stop(stop_sequence: str, turn_number: int) -> None:
    """处理 stop_sequence 命中事件"""
    if stop_sequence == "[DRIFT_DETECTED]":
        print(f"⚠️  第 {turn_number} 轮：模型自我检测到漂移，已截断")
        print(f"   → 建议：触发漂移恢复流程（升级到 v3 State Machine 自动处理）")
    elif stop_sequence in ("\n\nHuman:", "\n\nAssistant:"):
        print(f"👻 第 {turn_number} 轮：模型幻想额外对话回合，已截断")
        print(f"   → 命中序列: {repr(stop_sequence)}")
    else:
        print(f"ℹ️  第 {turn_number} 轮：命中停止序列: {repr(stop_sequence)}")


# ============================================================
# 动态 Temperature — 随轮次自动收紧
# ============================================================
# 对症：🙈 选择性遗忘 + 🎛️ 格式崩坏
# 原理：对话越长，模型注意力越分散，降低 temperature 强制概率分布集中

def get_dynamic_temperature(turn_number: int, base_temp: float = 0.3) -> float:
    """
    随对话轮次动态降低 temperature。

    分段策略：
    - 1-10 轮：保持基础 temperature（对话初期，不需要过度约束）
    - 11-30 轮：线性降低（对抗逐渐显现的注意力衰减）
    - 30+ 轮：保持最低值（此时应升级到 v2.5 或 v3）
    """
    if turn_number <= 10:
        return base_temp
    elif turn_number <= 30:
        # 每轮降低 0.01，最低到 0.05
        return max(0.05, base_temp - 0.01 * (turn_number - 10))
    else:
        return 0.05  # 30+ 轮维持最低温度


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    history = []
    task = "帮助用户分析财务报表，给出投资建议"

    for turn in range(1, 31):
        user_input = f"第{turn}轮的问题..."

        temp = get_dynamic_temperature(turn)

        response = create_drift_resistant_message(
            user_message=user_input,
            conversation_history=history,
            turn_number=turn,
            task_description=task,
            temperature=temp,
        )

        # 获取回复文本
        text = response.content[0].text if response.content else ""

        # --- 输出后处理（轻量版）---
        # 对于 Claude，由于没有 logit_bias，建议导入 output_post_filter 做深度过滤
        # from output_post_filter import PostFilter
        # text = PostFilter().clean(text)

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": text})

        # 如果连续漂移，考虑退出并升级方案
        if response.stop_reason == "stop_sequence":
            if response.stop_sequence == "[DRIFT_DETECTED]":
                print(f"第{turn}轮漂移，建议触发 v2.5 context compression 或 v3 恢复流程")
                break
