# Phase 7C2 Chat Research 状态 UI 审计

## 结论

候选来源为历史混合提交 `e3207a1` 中的六个 frontend 文件。本轮未 cherry-pick 该混合提交，而是对六文件进行最小化独立实现。六个文件均直接属于 Chat Research 状态展示切片，不包含其它前端功能。

## 六文件清单、用途与依赖

| 文件 | 直接用途 | 依赖关系 | 范围结论 |
|---|---|---|---|
| `frontend/src/utils/researchFulfillment.js` | 将后端 `fulfillment/reason_code` 转换为可展示状态，对来源、URL、覆盖与限制字段做白名单化 | 被 View 和 ThinkingPanel 引用 | 纳入 |
| `frontend/src/components/chat/ChatResearchStatusCard.vue` | 展示标题、说明、来源、as_of、覆盖、限制与状态化重试 | 由 MessageList 装配，只接收已清洗对象 | 纳入 |
| `frontend/src/components/chat/ChatThinkingMiniPanel.vue` | 终态标题与完成符号与真实 fulfillment 对齐 | 调用状态 Adapter | 纳入 |
| `frontend/src/components/chat/ChatMessageList.vue` | 在消息内装配状态卡，传递 fulfillment，按 retryable 控制重试入口 | 依赖 StatusCard 和 ThinkingPanel | 纳入 |
| `frontend/src/views/ChatCopilotView.vue` | 在同步响应、SSE 终态、历史恢复、超时与错误路径接入 Adapter | 依赖 Adapter，向 MessageList 传递清洗后模型 | 纳入 |
| `frontend/src/tests/researchFulfillment.test.js` | 验证四状态、五个 reason 文案、五种验收响应及组件接线 | 直接测试 Adapter，静态校验组件装配 | 纳入 |

```text
ChatCopilotView
  → researchFulfillment Adapter
  → ChatMessageList
      → ChatResearchStatusCard
      → ChatThinkingMiniPanel
researchFulfillment.test
  → Adapter + component wiring
```

## 展示契约结论

| 后端状态 | 用户标题 | 完成勾选 | 重试 |
|---|---|---:|---:|
| `fulfilled` | 已完成研究 | 是 | 否 |
| `partial` | 部分完成 | 否 | 是 |
| `unavailable` | 当前缺少所需数据 | 否 | 默认否；仅网络超时理由可重试 |
| `failed` | 研究执行失败 | 否 | 是 |

已覆盖 `NO_APPROVED_NEWS_SOURCE`、`NO_APPROVED_INDUSTRY_NEWS_SOURCE`、`PROVIDER_NETWORK_TIMEOUT`、`PROVIDER_PERMISSION_DENIED`、`DATA_NOT_AVAILABLE` 的中文文案。不识别的 reason code 不直接显示，降级为通用数据不可用说明。

## 来源与信息泄漏门禁

- 有来源：展示来源、数据截至时间、数据覆盖范围、数据限制。
- 无来源：来源区仅展示“未获得可验证来源”。
- 只允许 `http/https` 且不含 URL 凭据的链接。
- 来源名称映射为公开名称或“已验证来源”，不直出内部 provider 标识。
- Adapter 仅产出明确白名单字段；raw chunk ID、Token、Cookie、内部表名、数据库连接串、堆栈和调试字段不会进入展示对象。

## 工作树隔离取证

提交前的完整 `git diff --name-only` 显示了五个既有、非本阶段后端改动：

```text
backend/Dockerfile
backend/app/main.py
backend/app/services/report_embedding_provider.py
backend/pyproject.toml
backend/uv.lock
frontend/src/components/chat/ChatMessageList.vue
frontend/src/components/chat/ChatThinkingMiniPanel.vue
frontend/src/views/ChatCopilotView.vue
```

其对应完整 `git diff --stat` 为：

```text
8 files changed, 704 insertions(+), 9 deletions(-)
```

未跟踪文件不会出现在 `git diff` 中；已用 `git status --short` 另行核对。本阶段只暂存六个 frontend 文件和三份交付文档，上述五个后端改动及其它历史未跟踪文件保持未暂存。

## 边界

本轮未修改后端业务逻辑、Tushare Gateway、CNINFO 读取、Provider、Prompt、RAG、numeric/citation validation、Company V2、Docker、依赖或 migration；未调用 live Provider，未部署。
