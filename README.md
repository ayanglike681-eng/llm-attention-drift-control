# LLM 注意力漂移控制

> 模型在长对话中逐渐遗忘初始约束。三层方案，从复制粘贴到生产级状态机。灵感来源于日本山梨大学先进生物技术中心的若山照彦教授研究小鼠的克隆epigenetic reprogramming不完整性问题。

---

## 核心洞察

注意力漂移不是 token 采样的 bug。

更像是结构性的信息损失现象：封闭生成循环中，每轮复制都在降低原始信号的保真度。模型丢失了那个告诉它哪些指令重要的认识框架，

本项目把症状当作热力学事实处理。

---

## 三层方案

一条因果链。

| 层 | 解决的问题 | 一句话 | 怎么用 |
|----|-----------|--------|--------|
| **L1: Prompt** | 模型不知道"自己该是谁" | 定义应然 | 复制粘贴 system prompt |
| **L2: Context** | 模型忘了"之前说过什么" | 维护记忆 | 一行命令压缩对话历史 |
| **L3: State** | 模型在错误时间做错误事 | 结构行动 | 状态机限制行为边界 |

```
L1 "定义应然"        →    L2 "维护记忆"       →    L3 "结构行动"
Prompt 设定角色/规则      压缩防止约束"沉底"        状态门控限制行为半径
      ↓                       ↓                       ↓
  短对话够用             30轮后需要               复杂任务需要
```

> 这里没有纳入 `logit_bias`、`frequency_penalty` 这类 API 采样参数，主要原因在于它们解决"模型说了什么词"（症状），三层解决"模型在想什么"（病因）。对参数感兴趣可参见 [`reference/api-params.md`](reference/api-params.md)。

---

## 快速导航

| 你是谁 | 去哪里 |
|--------|--------|
| 用 ChatGPT/Claude 网页版，不知道选哪层 | [`START_HERE.md`](START_HERE.md) |
| 只想复制粘贴，不想读文档 | [`v1-prompt/QUICKSTART.md`](v1-prompt/QUICKSTART.md) |
| 写代码/调 API，对话超过 30 轮模型开始忘事 | [`v2-context/QUICKSTART.md`](v2-context/QUICKSTART.md) |
| 做复杂 Agent，模型行为混乱 | [`v3-state-machine/QUICKSTART.md`](v3-state-machine/QUICKSTART.md) |
| 想看实际效果对比 | [`examples/`](examples/) |
| 想理解原理和设计决策 | 各层 `README.md` |

---

## 设计原则

`temperature`、`top_p`、`frequency_penalty` 调整的是采样分布。它们改变“模型说了什么词”。

注意力漂移是认知框架的偏移。三层方案改变“模型认为自己是谁”。

**封闭系统必然漂移**

长对话中，每轮生成都是对前一轮的有损复制。原始信号（system prompt、用户约束、关键事实）在上下文窗口中逐渐沉底，被后续噪声覆盖。

三层方案的本质相同，都是向封闭循环注入系统内部已不存在的信号。

- L1：在每次对话起点重申原始约束
- L2：把过长的历史压缩为摘要，作为外部记忆重新注入
- L3：用状态机强制注入结构化的行为边界

---

## 同构

### 小鼠与模型

若山照彦教授在山梨大学先进生物技术中心研究小鼠的克隆 epigenetic reprogramming 不完整性问题。他发现小鼠连续克隆在第 58 代后不再具有繁殖后代的可能——第 58 代诞生的小鼠要么是 DNA 出现残缺，要么是 表达出现问题。

只有引入外部基因组，谱系才得以恢复。

误差是同一条曲线。

大模型每轮生成是一次复制。训练数据是对世界的有损采样，都是不可逆的过程。

涌现的上限是训练集的信息量，不是世界本身。

在被单一领域数据扭曲的封闭概率空间里，涌现只能重排已有元素。它的天花板是该领域的边界，不是人类认知的边界。

没有外部校验，信号与噪声在信息论上不可区分。

更多参数加更多领域数据，不是在开窗——是在打磨镜子。

---

## 哲学立场

本仓库不是模型升级。是一套开窗工具包。

我们不相信据此可以解决漂移，漂移是自回归生成架构中写入的第二定律。

但是我们相信工程化的可控熵减周期性、结构化、向封闭循环注入外部信号。


---

## 目录结构

```
.
├── START_HERE.md                 # 从这里开始
├── README.md                     # 本文件（总览 + 原理）
│
├── examples/                     # 效果对比
│   └── README.md
│
├── v1-prompt/                    # L1: Prompt Layer
│   ├── QUICKSTART.md             # 复制粘贴指南
│   ├── README.md                 # 原理 + 设计说明
│   ├── system_prompt_zh.md       # 中文 prompt（直接复制）
│   └── system_prompt_en.md       # English prompt
│
├── v2-context/                   # L2: Context Layer
│   ├── QUICKSTART.md             # 一键跑通指南
│   ├── README.md                 # 原理 + schema 设计
│   ├── run_compressor.py         # 一键压缩脚本
│   ├── memory_extractor.py       # 核心提取器
│   ├── output_post_filter.py     # 输出后处理
│   ├── colab_demo.ipynb          # 在线体验
│   ├── state_summary_schema.json # 结构化 schema
│   └── examples/
│       ├── 50_turn_demo.md
│       └── sample_conversation.json
│
├── v3-state-machine/             # L3: State Layer
│   ├── QUICKSTART.md             # 两条路径指南
│   ├── README.md                 # 原理 + 状态设计
│   ├── langgraph_template/
│   │   ├── README.md
│   │   ├── minimal_example.py    # 最简可跑
│   │   └── advanced/             # 完整版（7 状态）
│   └── dify_template/
│       ├── README.md
│       └── drift_control_workflow.yml
│
├── reference/                    # 补充参考
│   └── api-params.md
│
└── docs/                         # 通用文档
    ├── benchmark_methodology.md
    └── known_limitations.md
```

---

## 开始

不确定该用哪一层？从 [`START_HERE.md`](START_HERE.md) 的决策树开始。

一个问题，30 秒内指向正确的层。

---

## 限制与边界

这些层不消灭漂移。它们延缓漂移，并使其可被观测。

它们不提升模型的知识天花板。它们防止模型遗忘已知。

它们不能替代 RAG、工具调用或人类介入。它们是使这些干预生效的结构基础。

---

## 许可证

MIT License — 见 [LICENSE](LICENSE)。
