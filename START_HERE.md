# 从这里开始。30 秒找到你需要的。

---

## 你是哪种用户？

**👤 我用 ChatGPT / Claude 网页版聊天**
经常聊着聊着它忘记我一开始说的要求。

→ **只需要 L1。** 打开 [`v1-prompt/system_prompt_zh.md`](v1-prompt/system_prompt_zh.md)，全选复制，粘贴到对话设置里。完毕。

→ 不会设置？看 👉 [`v1-prompt/QUICKSTART.md`](v1-prompt/QUICKSTART.md)（有截图级别指引）

---

**👩‍💻 我在写代码 / 调 API，对话超过 30 轮后模型开始忘事**

→ **需要 L2。** 这是上下文压缩层——把 50 轮对话压缩成一段摘要，让模型"记住"关键信息。

→ 立刻试效果 👉 [`v2-context/QUICKSTART.md`](v2-context/QUICKSTART.md)（一条命令跑通）

→ 不想装环境？👉 [Colab 在线体验](v2-context/colab_demo.ipynb)（点开就能跑）

---

**🏗️ 我在做复杂 Agent / 多阶段任务，模型在错误的时间做错误的事**

→ **需要 L3。** 这是状态机层——定义每个阶段"能做什么、不能做什么"。

→ 用 Dify（可视化拖拽）👉 [`v3-state-machine/dify_template/`](v3-state-machine/dify_template/)

→ 用 LangGraph（Python 代码）👉 [`v3-state-machine/QUICKSTART.md`](v3-state-machine/QUICKSTART.md)（5 分钟跑通最简版）

---

## 还拿不准？

看 [`examples/`](examples/) 目录——每个例子展示同一段对话**用和不用**各层的对比。看效果再决定。

---

## 想理解原理？

各层 README 有完整的设计文档、因果分析、局限说明：

| 层 | README | 适合谁 |
|----|--------|--------|
| L1: Prompt | [`v1-prompt/README.md`](v1-prompt/README.md) | 想知道"为什么这几行 prompt 有效"的人 |
| L2: Context | [`v2-context/README.md`](v2-context/README.md) | 想知道"压缩器会不会二次幻觉"的人 |
| L3: State | [`v3-state-machine/README.md`](v3-state-machine/README.md) | 想知道"状态机为什么不消灭漂移、只围堵漂移"的人 |
