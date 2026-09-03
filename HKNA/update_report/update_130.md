# Update 130 - Phase 7C2 Chat Research 状态真实性 UI

## 1. 本次任务目标

将 Chat API 的 `fulfilled`、`partial`、`unavailable`、`failed` 研究状态如实呈现在前端，消除无数据或失败时仍显示“已完成分析”的误导。

## 2. 已完成内容

- 核实历史候选中六个 frontend 文件的用途和依赖，确认均属于状态展示切片。
- 新增研究状态 Adapter，统一标题、说明、reason 中文文案、重试策略与完成勾选。
- 新增简洁的研究状态卡，有来源时展示来源、as_of、覆盖与限制；无来源时仅告知未获得可验证来源。
- 修正思考过程卡终态，只有 `fulfilled` 显示完成勾选。
- 在同步响应、SSE 终态、历史恢复、超时和错误路径统一接入状态适配。
- 增加五种核心响应和信息泄漏防护测试。

## 3. 修改文件

- `frontend/src/utils/researchFulfillment.js`
- `frontend/src/components/chat/ChatResearchStatusCard.vue`
- `frontend/src/components/chat/ChatThinkingMiniPanel.vue`
- `frontend/src/components/chat/ChatMessageList.vue`
- `frontend/src/views/ChatCopilotView.vue`
- `frontend/src/tests/researchFulfillment.test.js`
- `backend/docs/artifacts/phase7c2_chat_status_ui_audit.md`
- `backend/docs/artifacts/phase7c2_chat_status_ui_runtime.md`
- `HKNA/update_report/update_130.md`

## 4. 测试与验收结果

- `npm test`：67 个测试文件、756 项测试全部通过。
- `npm run build`：构建通过，971 个模块完成转换。
- CNINFO fulfilled、EOD partial、行业新闻 unavailable、超时 failed、市场概览 partial 五种契约全部通过。
- 未执行 live Provider 调用，未修改后端、Docker、依赖或 migration。

## 5. 当前运行状态

前端 Candidate 可正确区分四种 fulfillment 状态。来源区仅使用白名单字段，未批准来源不会被包装为研究事实。

## 6. 风险与注意事项

- 只有后端实际传递 fulfillment metadata 的响应才会显示新状态卡；旧响应保持原有展示，前端不推测研究结果。
- `partial` 允许重试；无已批准来源、无权限或数据不存在的 `unavailable` 不提供无意义重试。
- 工作树中既有后端与历史未跟踪改动不属于本阶段，不应纳入本次提交。

## 7. 后续建议

- 后续如扩展 reason code，应先补充公开文案映射和适配器测试，不直接显示后端原始值。
- 可在获得可控的本地响应 fixture 后补充端到端视觉回归，不需要调用 live Provider。
