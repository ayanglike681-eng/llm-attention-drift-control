# L1 Quickstart — 复制粘贴，30 秒搞定

> 原理？不急。先让效果跑起来。想深究的看 [README.md](README.md)。

---

## 操作步骤

### 第 1 步：打开 Prompt 文件

- 中文对话 → [`system_prompt_zh.md`](system_prompt_zh.md)
- English → [`system_prompt_en.md`](system_prompt_en.md)

### 第 2 步：替换任务描述

文件里有一个 `{TASK_DESCRIPTION}`。把它换成你的实际任务。比如：

```
改前：你的核心任务是：{TASK_DESCRIPTION}
改后：你的核心任务是：帮我写技术文档，风格参考 Google 开发者指南，保持简洁客观。
```

### 第 3 步：粘贴到对应位置

| 你用的平台 | 粘贴到哪里 |
|-----------|-----------|
| **Claude.ai** | 设置 → 自定义指令 / Custom Instructions |
| **ChatGPT** | 设置 → Custom Instructions → "What would you like ChatGPT to know about you?" |
| **Claude API** | `system` 参数 |
| **OpenAI API** | `messages[0]` 的 `role: "system"` |
| **Dify** | 应用编排 → 系统提示词 |
| **LangChain** | `SystemMessage(content=...)` 或 `ChatPromptTemplate` |
| **其他 Chat 客户端** | 找设置里的 System Prompt / 自定义指令 / 人设 字段 |

### 第 4 步：开始对话

粘贴完直接开始聊。不用调任何参数。

---

## Token 紧张？用精简版

把上面的内容替换为这一段：

```
你是高可靠性助手。核心任务：{TASK_DESCRIPTION}

规则：
1. 每次回复前自检：理解问题？记住核心任务？格式正确？
2. 每5轮开头加：[状态: 第N轮 | 记忆清晰 | 约束OK]
3. 偏离时先声明再纠正
4. 回复格式：确认理解 → 正文 → 自检结果
```

---

## 效果不明显？

→ 升级到 [L2 Context Layer](../v2-context/QUICKSTART.md)（对话超过 30 轮后推荐）

→ 读原理：[README.md](README.md)
