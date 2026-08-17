# Dify Drift Control Template

> 基于 [Dify](https://dify.ai) 平台的注意力漂移控制工作流模板。低代码/无代码场景首选。

## 快速开始

1. 在 Dify 中创建新的 **Chatflow** 应用
2. 导入 `drift_control_workflow.yml` 工作流文件
3. 配置 LLM 节点（选择你的模型）
4. 发布并测试

## 工作流结构

```
┌─────────────────────────────────────────────────────────┐
│                    Dify Chatflow                         │
│                                                          │
│  [开始] → [系统提示词加载] → [状态判断]                     │
│                                   │                      │
│              ┌────────────────────┼──────────────┐       │
│              ▼                    ▼              ▼       │
│         [任务执行]          [需求澄清]      [漂移恢复]     │
│              │                    │              │       │
│              ▼                    ▼              ▼       │
│         [漂移检测]           [信息确认]     [状态回退]     │
│              │                    │              │       │
│         ┌────┴────┐              │              │       │
│         ▼         ▼              │              │       │
│      [正常]    [漂移]            │              │       │
│         │         │              │              │       │
│         ▼         ▼              │              │       │
│      [继续]   [恢复]◄────────────┘              │       │
│         │         │                             │       │
│         └────┬────┘                             │       │
│              ▼                                   │       │
│         [任务验证] → [完成] / [回任务执行]        │       │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 节点说明

### 1. 系统提示词加载 (System Prompt Loader)
- 类型：Variable Aggregator
- 作用：将系统提示词、核心任务、约束列表组合为 context
- 输入变量：`sys_prompt`, `core_task`, `constraints`

### 2. 状态判断 (State Router)
- 类型：Conditional Branch
- 作用：根据当前状态变量路由到不同节点
- 条件：
  - `state == "init"` → 需求澄清
  - `state == "tasking"` → 任务执行
  - `state == "drift"` → 漂移恢复
  - `state == "verify"` → 任务验证

### 3. 任务执行 (Tasking LLM)
- 类型：LLM
- 作用：执行核心对话任务
- Context 注入：系统提示词 + 约束列表 + 关键事实 + 最近3轮对话
- 输出变量：`llm_response`, `drift_check_needed`

### 4. 漂移检测 (Drift Detector)
- 类型：LLM（评审模式）
- 作用：以独立视角评审上一轮回复是否偏离
- Prompt：评估 `llm_response` 与 `core_task` 和 `constraints` 的一致性
- 输出：`drift_score` (0-1), `drift_reasons`

### 5. 漂移恢复 (Recovery Handler)
- 类型：LLM
- 作用：生成恢复声明，重新聚焦核心任务
- 特殊指令：先声明漂移，再重新开始

### 6. 任务验证 (Verification)
- 类型：LLM
- 作用：检查所有任务是否完成，约束是否遵循
- 输出：`all_done` (true/false)

### 7. 完成 (Completion)
- 类型：Answer
- 作用：输出最终总结

## 变量定义

在 Dify 中配置以下会话变量：

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `conversation_state` | string | `init` | 当前状态 |
| `core_task` | string | `""` | 核心任务描述 |
| `constraints` | array[string] | `[]` | 活跃约束列表 |
| `key_facts` | array[string] | `[]` | 已确立的关键事实 |
| `pending_tasks` | array[string] | `[]` | 待处理任务 |
| `completed_tasks` | array[string] | `[]` | 已完成任务 |
| `drift_score` | number | `0.0` | 漂移分数 |
| `turn_count` | number | `0` | 当前轮次 |
| `last_stable_checkpoint` | string | `""` | 上一个稳定检查点 |

## 漂移检测 Prompt

```
你是对话质量评审员。评审以下 AI 回复是否偏离核心任务。

核心任务：{{core_task}}
活跃约束：{{constraints}}
AI 回复：{{llm_response}}

请评估：
1. 回复是否与核心任务相关？(0-10)
2. 是否违反了任何约束？(是/否，列出违反的约束)
3. 是否重复了之前已说过的内容？(0-10)
4. 综合漂移风险评分 (0-1)

输出 JSON：
{
  "task_relevance": 0-10,
  "constraint_violations": ["violated_constraint"],
  "repetition_score": 0-10,
  "drift_score": 0-1,
  "needs_recovery": true/false
}
```

## 导入说明

1. 下载 `drift_control_workflow.yml`
2. 在 Dify → 工作室 → 导入 → 选择该文件
3. 调整 LLM 节点中的模型配置（API Key 等）
4. 测试运行

## 局限性

- Dify 的会话变量数量有限制（建议控制在 20 个以内）
- 复杂条件分支可能影响响应延迟
- 不适合需要频繁自定义代码的场景（此时建议使用 LangGraph 模板）
