# LLM Attention Drift Control

> 模型聊着聊着就忘了你在说什么？三层方案，从复制粘贴到生产级状态机。

---

## 🚀 不知道选哪层？点这个

👉 **[START_HERE.md](START_HERE.md)** — 30 秒，回答一个问题，告诉你该用哪层。

或者直接看效果：[`examples/`](examples/) — 同一段对话，用和不用差多少。

---

## 什么是 Attention Drift？

LLM 在长对话中逐渐"走神"：遗忘早期指令、忽略约束条件、回复质量下降、产生幻觉。

它的本质不是"模型输出了某些不该说的词"——而是**模型对自己应该关注什么、记住什么、扮演什么角色的认知发生了偏移**。

---

## 三层方案

这不是三个孤立的工具，而是一条**因果链**：

| 层 | 解决的问题 | 一句话 | 怎么用 |
|----|----------|--------|--------|
| **L1: Prompt** | 模型不知道"自己该是谁" | 定义应然 | 复制粘贴 system prompt |
| **L2: Context** | 模型忘了"之前说过什么" | 维护记忆 | 一行命令压缩对话历史 |
| **L3: State** | 模型在错误时间做错误事 | 结构行动 | 状态机限制行为边界 |

```
L1 "定义应然"        →    L2 "维护记忆"       →    L3 "结构行动"
Prompt 设定角色/规则      压缩防止约束"沉底"        状态门控限制行为半径
      ↓                       ↓                       ↓
  短对话够用             30轮后需要               复杂任务需要
```

> 我们没有纳入 `logit_bias`、`frequency_penalty` 这类 API 采样参数。它们解决"模型说了什么词"（症状），三层解决"模型在想什么"（病因）。对参数感兴趣 → [`reference/api-params.md`](reference/api-params.md)。

---

## 你来这里是为了

| 你是 | 去这里 |
|------|--------|
| 👤 用 ChatGPT/Claude 网页版，不知道选哪层 | [`START_HERE.md`](START_HERE.md) |
| 🔰 只想复制粘贴，不想读文档 | [`v1-prompt/QUICKSTART.md`](v1-prompt/QUICKSTART.md) |
| 👩‍💻 写代码/调 API，对话超过 30 轮模型开始忘事 | [`v2-context/QUICKSTART.md`](v2-context/QUICKSTART.md) |
| 🏗️ 做复杂 Agent，模型行为混乱 | [`v3-state-machine/QUICKSTART.md`](v3-state-machine/QUICKSTART.md) |
| 📊 想看实际效果对比 | [`examples/`](examples/) |
| 🧠 想理解原理和设计决策 | 各层 `README.md` |
| 🎨 想看信息论同构的艺术化叙事 | [`art/index.html`](art/index.html) |

---

## 目录结构

```
.
├── START_HERE.md                 # 👈 从这里开始
├── README.md                     # 本文件（总览 + 原理）
│
├── examples/                     # 效果对比（不看原理看效果）
│   └── README.md
│
├── v1-prompt/                    # L1: Prompt Layer
│   ├── QUICKSTART.md             #    复制粘贴指南
│   ├── README.md                 #    原理 + 设计说明
│   ├── system_prompt_zh.md       #    中文 prompt（直接复制）
│   └── system_prompt_en.md       #    English prompt (copy & paste)
│
├── v2-context/                   # L2: Context Layer
│   ├── QUICKSTART.md             #    一键跑通指南
│   ├── README.md                 #    原理 + schema 设计
│   ├── run_compressor.py         #    一键压缩脚本
│   ├── memory_extractor.py       #    核心提取器
│   ├── output_post_filter.py     #    输出后处理
│   ├── colab_demo.ipynb          #    在线体验（零安装）
│   ├── state_summary_schema.json #    结构化 schema
│   └── examples/
│       ├── 50_turn_demo.md
│       └── sample_conversation.json
│
├── v3-state-machine/             # L3: State Layer
│   ├── QUICKSTART.md             #    两条路径指南
│   ├── README.md                 #    原理 + 状态设计
│   ├── langgraph_template/
│   │   ├── README.md
│   │   ├── minimal_example.py    #    最简可跑（从这里开始）
│   │   └── advanced/             #    完整版（7 状态）
│   └── dify_template/
│       ├── README.md
│       └── drift_control_workflow.yml
│
├── reference/                    # 补充参考
│   └── api-params.md
├── docs/                         # 通用文档
│   ├── benchmark_methodology.md
│   └── known_limitations.md
│
└── art/                          # 艺术化叙事
    └── index.html                #    滚动叙事 · 信息论同构 · self-contained
```
