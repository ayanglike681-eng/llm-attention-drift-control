# L3 Quickstart — 两条路，选你顺手的

> L3 用状态机把模型的发散半径限制在单个状态内。原理 → [README.md](README.md)。

---

## 选你的路径

```
你会用 Dify（可视化拖拽）？
  ├─ 是 → 路径 A：导入 workflow 文件，拖拽即用（3 分钟）
  └─ 否，我写 Python → 路径 B：跑 minimal_example.py（5 分钟）
```

---

## 路径 A：Dify（零代码）

### 你需要
- 一个 Dify 账号（cloud.dify.ai 或自部署）

### 步骤

1. 登录 Dify → 工作室 → 创建应用 → **Chatflow**
2. 右上角 → 导入 → 选择 [`dify_template/drift_control_workflow.yml`](dify_template/drift_control_workflow.yml)
3. 点开每个 LLM 节点 → 配置你的模型 API Key
4. 点「发布」
5. 开始对话

导入后的工作流包含 7 个节点（状态路由 → 任务执行 → 漂移检测 → 漂移恢复），开箱即用。

详细配置 → [`dify_template/README.md`](dify_template/README.md)

---

## 路径 B：LangGraph（Python）

### 你需要
- Python 3.10+
- OpenAI API Key

### 步骤

```bash
# 1. 安装
pip install langgraph langchain-openai

# 2. 设置 API Key
export OPENAI_API_KEY="sk-..."

# 3. 跑最简版（3 个状态，5 分钟跑通）
cd langgraph_template
python minimal_example.py

# 4. 对话测试
# 👤 You: 帮我分析这个数据
# 🤖 [research]: ...（分析中，不会给建议）
# 👤 You: 给我建议
# 🤖 [decision]: ...（自动切换到决策模式）
```

跑通后想看完整版（7 状态 + drift recovery + checkpoint）→ [`langgraph_template/advanced/`](langgraph_template/advanced/)

---

## 效果示例

**不用 L3（无状态控制）：**
```
用户: 帮我分析这组数据
AI: [分析] ... 
用户: 数据好像有问题
AI: [建议] 你应该用另一个工具...
     ↑ 模型跳过了"确认问题"直接给建议——它在错误的阶段做了错误的事
```

**用了 L3：**
```
用户: 帮我分析这组数据
AI: [research 状态 - 分析中] 从数据来看，趋势是...
用户: 给我建议
AI: [切换到 decision 状态] 基于分析，我建议...
     ↑ 模型被 FORBIDDEN 列表约束，不会在 research 状态下给建议
```

---

## 想深入定制？

→ 完整模板：[`langgraph_template/advanced/`](langgraph_template/advanced/)（7 状态 + drift recovery）

→ 原理：[README.md](README.md)
