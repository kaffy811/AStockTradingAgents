---
目前完成的工作汇总：

已完成

1. Phase 7D-P0.5 隔离候选集成
- 从 `5dad7228...` 创建 detached worktree 与隔离审计分支。
- 按指定顺序无冲突 replay 三个提交，集成 SHA 为 `c812d4d2...`。
- 候选 tree 与来源末端提交 tree 完全一致，未纳入主工作区脏改。

2. 范围与公开响应安全审计
- 完成 baseline→candidate 18 文件全量 diff 分类；未发现禁止类别变更。
- 验证 history 正向 allowlist、受控 warning、EOD DTO 去内部字段、profile 固定异常文案和 debug/raw 鉴权边界。

3. 构建前门禁
- 后端相关回归：106 passed。
- 前端完整门禁：69 files / 764 tests passed，0 worker timeout。
- frontend production build、Python compile、JSON validation、secret scan、git diff --check 均通过。

4. Q1–Q4 串行验收
- Q1、Q2、Q4 受控 fixture 验证通过。
- Q3 有报告期、来源、as_of、ROE 与估值，但 `numeric_validation=null`，不满足发布条件。

5. Release 决策与证据
- 决策为 `HOLD_WITH_EVIDENCE`。
- Docker daemon 不可连接，无法生成 fresh backend/frontend 纯镜像及完成镜像 provenance/security 验证。
- 详细报告与机器可读 manifest 已写入 `backend/docs/artifacts/`。

---
下一步：你需要操作

第一步：启动可用的 Docker daemon，并从 integrated candidate `c812d4d2e572ffd08cfd56b8110c0ba87b0cab05` 的干净 tree 构建 backend/frontend 镜像；OCI revision 必须使用完整候选 SHA。

第二步：核对镜像 `Mounts=[]`、config/history、关键源码 hash 与 Git tree，并扫描响应样本和镜像元数据中的 Token、Authorization、数据库连接串。

第三步：为 Q3 提供已批准的 numeric validation 证据后，在同一纯镜像环境逐条、串行、无重试执行 Q1–Q4；保存响应与所有禁止 Provider 的调用计数。

第四步：技术门禁全部通过后再请求 Owner 审批；公开部署仍需 Owner 确认 Tushare 商业展示、缓存和 AI 摘要使用权。
