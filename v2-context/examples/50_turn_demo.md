# 50 轮对话压缩演示

> 模拟一段 50 轮的技术支持对话，展示上下文压缩前后的对比。

---

## 场景设定

- **角色**：AI 技术支持助手
- **用户**：某 SaaS 平台的开发者
- **任务**：排查 API 集成问题，同时讨论最佳实践
- **核心约束**：使用 Python SDK v2.x，需要兼容 PostgreSQL

---

## 原始对话（50轮，约 15K tokens）

### 轮次 1-10：问题描述与初步排查

```
Turn 1  | User: 我们的 API 调用一直返回 403 错误，帮忙看看
Turn 1  | AI: 好的，403 通常是认证问题。请问用的是哪个 SDK 版本？
Turn 2  | User: Python SDK v2.1.3
Turn 2  | AI: 收到，v2.1.3 是最新版。请确认 API key 是否正确设置？
Turn 3  | User: API key 是对的，其他接口能正常调用。只有 /data/export 这个接口报 403
Turn 3  | AI: /data/export 需要额外的 Data Export 权限。请在控制台 → 权限管理 → 数据导出 中开启
Turn 4  | User: 找到了！原来需要单独开。开启了，现在返回 200 但数据为空
Turn 5  | AI: 数据为空可能是因为查询时间段内没有数据。请确认时间范围参数
Turn 5  | User: 时间范围是 2024-01-01 到 2024-01-31，应该有数据的
Turn 6  | AI: 让我确认一下：您用的是 `export_data(start, end)` 还是 `query_export(params)`？
Turn 6  | User: 用的 `export_data(start_date, end_date)`，按文档来的
Turn 7  | AI: 文档那页有个 typo——参数名应该是 `start` 和 `end`，不是 `start_date` 和 `end_date`
Turn 7  | User: 😤 改了还是不行
Turn 8  | AI: 检查一下时区设置，默认是 UTC。您的数据可能在 UTC+8
Turn 8  | User: 怎么设置时区？
Turn 9  | AI: 在 client 初始化时传入 `timezone="Asia/Shanghai"`
Turn 9  | User: 可以了！数据出来了！顺便问一下，这个 API 支持异步调用吗？
Turn 10 | AI: 支持的，v2.1.0+ 版本可以用 `async_export_data()` 方法
Turn 10 | User: 好的，我们先继续看别的问题...
```

### 轮次 11-20：数据库兼容性讨论

```
Turn 11 | User: 我们的数据库是 PostgreSQL 15，有什么需要注意的吗？
Turn 11 | AI: PostgreSQL 15 完全兼容。注意 `jsonb` 字段的查询语法略有不同
Turn 12 | User: 具体怎么不同？
Turn 12 | AI: 使用 `->>` 操作符代替 `->`，例如 `data->>'name'` 而不是 `data->'name'`
Turn 13 | User: 我们现在用的是 MySQL 8.0，迁移到 PG 有什么风险？
Turn 13 | AI: 主要差异在：1) 自增主键语法 2) JSON 函数 3) 事务隔离级别默认值
Turn 14 | User: 能详细说说事务隔离级别吗？
Turn 14 | AI: MySQL 默认 REPEATABLE READ，PG 默认 READ COMMITTED。建议显式设置
Turn 15 | User: 我们目前线上跑的是 MySQL，短期内不迁移。先用 MySQL 测试吧
Turn 15 | AI: 了解，MySQL 8.0 也在支持范围内。有具体问题随时问
Turn 16 | User: 等一下，刚才说的 PostgreSQL 跟我们的场景有什么关系？
Turn 16 | AI: 抱歉造成了困惑。之前提到 PG 是因为您在 Turn 11 问 PG 15 的注意事项。既然短期不迁移，我们聚焦 MySQL
Turn 17 | User: 对，专注 MySQL。回到 API 问题——分页怎么处理？
Turn 18 | AI: 使用 `page` 和 `page_size` 参数。默认 page_size=20，最大 100
Turn 18 | User: 那个 `total_count` 字段有时返回 null，是 bug 吗？
Turn 19 | AI: 不是 bug。当结果集超过 10000 条时，total_count 会返回 null 以优化查询性能
Turn 19 | User: 这个限制在哪里文档有写？
Turn 20 | AI: 在 API Reference → Pagination → Known Limitations 章节
Turn 20 | User: 找到了，谢谢。对了，导出的数据格式可以选 CSV 吗？
```

### 轮次 21-30：数据导出与格式

```
Turn 21 | AI: 可以的，设置 `format="csv"` 即可。支持 CSV、JSON、Parquet 三种格式
Turn 21 | User: Parquet 格式怎么用？我们数据量大
Turn 22 | AI: `export_data(start, end, format="parquet", compression="snappy")`
Turn 22 | User: 需要装什么依赖吗？
Turn 23 | AI: SDK 内置了 parquet 支持，但需要 `pip install pyarrow` 以启用压缩
Turn 23 | User: 好，装了。导出 100 万行数据大概多久？
Turn 24 | AI: 大约 2-5 分钟，取决于字段数量和网络带宽。可以用异步方法避免超时
Turn 24 | User: 异步方法返回一个 task_id，然后怎么查询进度？
Turn 25 | AI: 用 `get_export_status(task_id)` 轮询，或设置 webhook 接收完成通知
Turn 25 | User: webhook 怎么配？
Turn 26 | AI: 在 `client.configure_webhook(url, events=["export.completed"])` 中设置
Turn 26 | User: 这需要我们的服务器暴露公网端点吧？
Turn 27 | AI: 是的。如果不行，建议用轮询方式，每 5 秒查一次
Turn 27 | User: 我们用轮询。还有个小问题——导出的 CSV 中文乱码
Turn 28 | AI: CSV 默认 UTF-8 编码。如果 Excel 打开乱码，加 BOM：`encoding="utf-8-sig"`
Turn 28 | User: 解决了！你们文档真的应该更新一下这些细节
Turn 29 | AI: 感谢反馈，我会记录这个建议。还有其他问题吗？
Turn 29 | User: 暂时没了，等我整合一下再问你
Turn 30 | AI: 好的，随时找我。总结一下今天我们解决的：403权限、参数名、时区、分页、导出格式
Turn 30 | User: 对，先确认这些
```

### 轮次 31-40：闲聊与跑题

```
Turn 31 | User: 说起来，你做 AI 客服多久了？（闲聊）
Turn 32 | AI: 我是 AI 助手，没有"多久"的概念。需要继续讨论 API 集成的问题吗？
Turn 32 | User: 哈哈开个玩笑。对了你们公司融资到哪轮了？
Turn 33 | AI: 我没有公司的融资信息。回到您的集成问题——还有什么需要帮助的吗？
Turn 33 | User: 好吧。那个 403 错误我再确认下...（重提已解决问题）
Turn 34 | AI: 403 问题已在 Turn 3-4 解决——原因是 /data/export 接口需要单独的 Data Export 权限
Turn 34 | User: 哦对对对，我忘了
Turn 35 | User: 所以现在都搞定了对吧？
Turn 36 | AI: 是的。回顾已解决的：403权限(T3)、参数名(T7)、时区(T9)、分页(T18)、导出格式(T22)、CSV编码(T28)
Turn 36 | User: 那帮我写个完整的调用示例吧
Turn 37 | AI: 好的，以下是一个完整的示例... [代码生成]
Turn 37 | User: 那个异步的也加上
Turn 38 | AI: [补充异步示例代码]
Turn 38 | User: 完美。哎你们支持 GraphQL 吗？
Turn 39 | AI: 目前只支持 REST API。GraphQL 在路线图中但没有具体时间表
Turn 39 | User: 好吧。那 REST 的 rate limit 是多少？
Turn 40 | AI: 免费版 100 req/min，专业版 1000 req/min，企业版 10000 req/min
Turn 40 | User: 我们是专业版，够用了
```

### 轮次 41-50：新问题与旧问题交织

```
Turn 41 | User: 突然发现 Webhook 回调收不到，帮我排查
Turn 42 | AI: 先确认 webhook URL 是否正确配置？用 `client.get_webhook_config()` 查看
Turn 42 | User: 配置是对的，但 callback 就是不来
Turn 43 | AI: 检查一下事件类型是否匹配。导出完成事件是 `export.completed`（注意有 s，不是 `export.complete`）
Turn 43 | User: 啊，我写的是 `export.complete` 😅
Turn 44 | AI: 这就是原因。修改后应该能收到了
Turn 44 | User: 收到了！话说之前解决的那些问题你还能记住吗？
Turn 45 | AI: 我回顾一下：403 → 权限；参数 → start/end；时区 → Asia/Shanghai；分页 → page/page_size；导出 → format+async；编码 → UTF-8 BOM
Turn 45 | User: 记忆力不错！最后一个问题：SDK 怎么升级到最新版？
Turn 46 | AI: `pip install --upgrade your-sdk`。但 v2.1.3 已是最新稳定版
Turn 46 | User: 我们好像一开始就是 2.1.3？
Turn 47 | AI: 是的，Turn 2 时您确认了使用 v2.1.3
Turn 47 | User: 那我没什么问题了。总结一下吧
Turn 48 | AI: [生成长篇总结，但遗漏了时区设置和 CSV 编码两个已解决问题]
Turn 48 | User: 你漏了时区和编码！
Turn 49 | AI: 抱歉！补充：时区 → `timezone="Asia/Shanghai"` (T9)；CSV编码 → `encoding="utf-8-sig"` (T28)
Turn 49 | User: 这才对
Turn 50 | AI: 更新后的完整总结... [正确总结所有已解决问题]
```

---

## 压缩结果

### 未压缩（原始上下文）

```
Token 估计：~15,000
包含：全部 50 轮对话原始文本
问题：Turn 48 时模型遗漏时区和编码问题 → 注意力漂移已发生
```

### v2.5 压缩后（注入 LLM 的上下文）

```markdown
## Conversation Summary
用户在使用 Python SDK v2.1.3 集成 SaaS API，数据库为 MySQL 8.0（暂不迁移 PG 15）。
已解决 7 个技术问题，当前正在收尾确认。最近在排查 webhook 回调问题。

## Active Constraints
- 使用 Python SDK v2.1.3（Turn 2, Turn 46确认仍是最新版）
- 数据库为 MySQL 8.0（Turn 15 确认暂不迁移）
- 专业版账号，rate limit 1000 req/min（Turn 40）
- 需要用异步方法处理大数据量导出（Turn 24）
- 使用轮询而非 webhook 查询导出进度（Turn 27 决定）

## Key Facts Established
- [T3-4] /data/export 接口需要单独的 Data Export 权限
- [T7] 参数名是 `start` 和 `end`，不是 `start_date`/`end_date`
- [T9] 时区设置为 `timezone="Asia/Shanghai"`
- [T18-19] 分页用 page/page_size，total_count 在 >10000 时返回 null
- [T22] 导出支持 CSV/JSON/Parquet，Parquet 需要 `pip install pyarrow`
- [T25-26] `async_export_data()` 返回 task_id，用 `get_export_status()` 轮询
- [T27] Webhook 也可用但需要公网端点
- [T28] CSV 中文乱码用 `encoding="utf-8-sig"` 解决
- [T43] Webhook 事件名是 `export.completed`（有 s）
- [T40] 专业版 rate limit: 1000 req/min

## Decisions Made
- 使用轮询方式查询异步导出进度（T27）
- 短期不迁移到 PostgreSQL（T15）
- 使用 UTF-8 BOM 解决 CSV 中文乱码（T28）

## Pending Items
- [ ] 更新文档中的参数名 typo（Turn 29 用户反馈）
- [ ] 补充 CSV 编码说明到文档（Turn 29 用户反馈）

## Recent Conversation (last 3 turns)
**User** (T49): 你漏了时区和编码！
**Assistant** (T49): 抱歉！补充：时区 → `timezone="Asia/Shanghai"` (T9)；CSV编码 → ...
**User** (T50): 这才对
**Assistant** (T50): 更新后的完整总结...
```

### 压缩效果对比

| 指标 | 压缩前 | 压缩后 |
|------|--------|--------|
| Token 数 | ~15,000 | ~2,200 |
| 压缩比 | - | 6.8:1 |
| 关键信息项 | 散落在50轮中 | 10条结构化事实 |
| 约束可见性 | 需自行推断 | 5条显式约束 |
| 模型遗漏风险 | 高（T48 已遗漏2项） | 低（结构化列表） |
| Token 节省 | - | ~85% |

---

## 关键观察

1. **闲聊是噪声源**：T31-T33 的闲聊对任务无贡献，应被丢弃
2. **重复确认可压缩**：T35/T36 的重述是冗余的，摘要只需保留一条
3. **结构化的力量**：将散落的 7 个解决方案整理为"Key Facts"列表后，模型不再遗漏
4. **约束持续可见**：即使对话跑题到 GraphQL (T38)，核心约束仍然保留在压缩结果中
5. **压缩时机**：理想情况下应在 T30 触发第一次压缩（问题告一段落），T44 触发第二次
