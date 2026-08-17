# L2 Quickstart — 一条命令看效果

> 把 50 轮对话压缩成一段摘要，让模型"记住"关键信息。原理 → [README.md](README.md)。

---

## 方式 1：本地跑（30 秒）

```bash
# 1. 安装（只需要 OpenAI SDK）
pip install openai

# 2. 设置 API key
export OPENAI_API_KEY="sk-..."

# 3. 跑示例对话
python run_compressor.py \
  --input examples/sample_conversation.json \
  --output summary.json

# 4. 看结果
cat summary.json
```

输入是一个 50 轮对话 JSON，输出是一个压缩后的结构化摘要（约 500 tokens）。

---

## 方式 2：在线跑（零安装）

打开 Colab notebook → 点 "全部运行" → 粘贴你的对话 → 拿结果。

👉 [`colab_demo.ipynb`](colab_demo.ipynb)（在 Google Colab 中打开）

---

## 拿到摘要后怎么用

把 `summary.json` 里的内容粘贴到下一轮对话的 **开头**（system prompt 后面），替换掉之前冗长的对话历史。格式像这样：

```
[你的原始 system prompt]

## 对话状态（由压缩器生成）
用户在使用 Python SDK v2.1.3 集成 API。已解决 403、时区、分页等问题。
关键约束：使用 MySQL 8.0，专业版账号 1000 req/min。
待处理：Parquet 导出最佳实践。

## 最近对话
User: Parquet 导出 100 万行大概多久？
Assistant: 约 2-5 分钟，建议用 async_export_data()...

---
请基于以上上下文回复用户的下一轮消息。
```

---

## 输入格式

对话历史 JSON 格式（和 OpenAI Chat API 的 messages 数组一样）：

```json
[
  {"role": "system", "content": "你是技术助手..."},
  {"role": "user", "content": "我的 API 返回 403..."},
  {"role": "assistant", "content": "403 通常是权限问题..."},
  {"role": "user", "content": "改了还是不行"},
  ...
]
```

参考 `examples/sample_conversation.json`。

---

## 效果不够好？

→ 升级到 [L3 State Machine](../v3-state-machine/QUICKSTART.md)（复杂多阶段任务）

→ 读原理：[README.md](README.md)（schema 设计、触发时机、二次幻觉风险）
