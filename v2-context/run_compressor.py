#!/usr/bin/env python3
"""
L2 Context Compressor — 一键压缩对话历史

用法:
    python run_compressor.py --input conversation.json --output summary.json

输入: 对话历史 JSON（标准 OpenAI messages 格式）
输出: 结构化压缩摘要 JSON
"""

import argparse
import json
import os
import sys

# 如果 openai 没装，给友好提示
try:
    from openai import OpenAI
except ImportError:
    print("❌ 需要安装 openai SDK: pip install openai")
    sys.exit(1)


def load_conversation(path: str) -> list[dict]:
    """加载对话历史 JSON"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("JSON 必须是数组格式 [{role: ..., content: ...}, ...]")
    return data


def estimate_tokens(conversation: list[dict]) -> int:
    """粗略估算 token 数（4 chars ≈ 1 token）"""
    return sum(len(m.get("content", "")) for m in conversation) // 4


def extract(conversation: list[dict], api_key: str, model: str = "gpt-4o-mini") -> dict:
    """
    调用 LLM 提取对话关键信息。

    使用 gpt-4o-mini 以降低成本和延迟——提取任务不需要强推理。
    """
    client = OpenAI(api_key=api_key)

    # 格式化对话
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

    conversation_text = "\n\n".join(lines)

    prompt = """你是对话分析员。从以下对话历史中提取关键信息。

输出严格的 JSON 格式（不要输出其他内容）：
{
  "summary": "3-5句中文摘要，概括对话当前状态",
  "constraints": [
    {"content": "约束内容", "established_at_turn": 轮次, "still_valid": true}
  ],
  "key_facts": [
    {"content": "事实内容", "source_turns": [轮次列表], "confidence": "confirmed|tentative"}
  ],
  "decisions": [
    {"content": "决策内容", "decided_at_turn": 轮次}
  ],
  "pending_items": [
    {"content": "待办内容", "raised_at_turn": 轮次, "status": "not_started|in_progress"}
  ]
}

规则：
1. constraints: 用户设定的规则、限制、格式要求。如果后续轮次推翻了某条，标记 still_valid: false。
2. key_facts: 用户提供的重要信息、数据。confidence: confirmed=多方确认, tentative=单次提及。
3. decisions: 对话中达成的共识、做出的选择。
4. pending_items: 未完成的任务、未回答的问题。
5. 闲聊、寒暄、重复内容不提取。

## 对话记录
""" + conversation_text

    # 如果对话太长，截断到约 30K chars
    if len(prompt) > 40000:
        prompt = prompt[:40000] + "\n\n[... 对话过长，已截断后续 ...]"

    print(f"📤 发送提取请求...（对话 {turn} 轮，约 {estimate_tokens(conversation)} tokens）")

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    return result


def format_for_llm(result: dict, recent_turns: list[dict]) -> str:
    """将提取结果格式化为可直接注入 LLM 的文本"""
    parts = []

    if result.get("summary"):
        parts.append(f"## 对话状态摘要\n{result['summary']}")

    constraints = [c for c in result.get("constraints", []) if c.get("still_valid", True)]
    if constraints:
        parts.append("\n### 活跃约束")
        for c in constraints:
            parts.append(f"- [T{c.get('established_at_turn', '?')}] {c['content']}")

    facts = [f for f in result.get("key_facts", [])
             if f.get("confidence") in ("confirmed", "tentative")]
    if facts:
        parts.append("\n### 已确立的关键事实")
        for f in facts:
            turns = ",".join(str(t) for t in f.get("source_turns", ["?"]))
            marker = "✅" if f.get("confidence") == "confirmed" else "⚠️"
            parts.append(f"- {marker} [T{turns}] {f['content']}")

    decisions = result.get("decisions", [])
    if decisions:
        parts.append("\n### 已做出的决策")
        for d in decisions:
            parts.append(f"- [T{d.get('decided_at_turn', '?')}] {d['content']}")

    pending = result.get("pending_items", [])
    if pending:
        parts.append("\n### 待处理事项")
        for p in pending:
            icon = {"not_started": "⬜", "in_progress": "🔄", "blocked": "🚫"}.get(
                p.get("status", "not_started"), "⬜")
            parts.append(f"- {icon} {p['content']}")

    if recent_turns:
        parts.append("\n---\n## 最近对话（保留原文）")
        for turn in recent_turns[-6:]:  # 最近 3 轮
            role = turn.get("role", "unknown").capitalize()
            content = turn.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            parts.append(f"\n**{role}**: {content}")

    parts.append("\n---")
    parts.append("以上为压缩后的上下文。请基于这些信息回复用户。")
    parts.append("如果摘要与最近对话原文矛盾，以原文为准。")

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="L2 Context Compressor — 一键压缩对话历史",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_compressor.py -i conversation.json -o summary.json
  python run_compressor.py -i conversation.json -o summary.json --model gpt-4o
        """,
    )
    parser.add_argument("--input", "-i", required=True, help="对话历史 JSON 文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出文件路径")
    parser.add_argument("--model", "-m", default="gpt-4o-mini",
                        help="提取用的 LLM 模型 (default: gpt-4o-mini)")
    parser.add_argument("--api-key", help="OpenAI API Key（也可通过 OPENAI_API_KEY 环境变量设置）")
    args = parser.parse_args()

    # API Key
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ 请设置 OPENAI_API_KEY 环境变量或用 --api-key 参数")
        print("   export OPENAI_API_KEY='sk-...'")
        sys.exit(1)

    # 加载
    conversation = load_conversation(args.input)
    turn_count = len([m for m in conversation if m["role"] != "system"]) // 2
    token_est = estimate_tokens(conversation)

    print(f"📂 已加载: {args.input}")
    print(f"   {turn_count} 轮对话, 约 {token_est} tokens")

    # 提取
    result = extract(conversation, api_key, args.model)

    # 保留最近 3 轮原文
    non_system = [m for m in conversation if m["role"] != "system"]
    recent = non_system[-6:] if len(non_system) >= 6 else non_system

    # 格式化
    formatted = format_for_llm(result, recent)

    # 输出
    output = {
        "input_turns": turn_count,
        "input_tokens_est": token_est,
        "output_tokens_est": len(formatted) // 4,
        "compression_ratio": f"{token_est}:{len(formatted) // 4}",
        "extraction": result,
        "formatted_for_llm": formatted,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 压缩完成 → {args.output}")
    print(f"   {token_est} tokens → ~{len(formatted) // 4} tokens")
    print(f"   压缩比: {output['compression_ratio']}")
    print(f"\n💡 下一步: 把 summary.json 中的 formatted_for_llm 字段内容")
    print(f"   粘贴到下一轮对话的 system prompt 后面，替换掉原始对话历史。")


if __name__ == "__main__":
    main()
