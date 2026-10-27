---
目前完成的工作汇总：

已完成

1. 只读核验 Phase 8A 候选 `c6f440d252cf6e61a65581807539030189416af1`：其父提交为生产基线 `dbf2073eb06a4206dea604a7156acae461c6bb35`，tree 为 `c8d05243c2f0ace8139263bbda4fa66175b8c680`，祖先关系、洁净候选工作树、完整 diff 和禁止路径范围检查通过。
2. 完成身份、权限、上下文、状态与审计契约复核。确认当前线上接入因缺少可信 Workspace 会返回 `ACTION_AUTH_REQUIRED`，但发现伪造 actor/workspace 和非法证券参数可通过 verification 并在受控假仓库中返回 succeeded；精确注入文本和歧义实体也未安全拒绝。
3. 复核 Phase 8A 已记录的后端、前端、build、compile、JSON、secret scan 和 diff check 结果，并登记缺失的注入、身份绑定、非法参数与歧义实体负向覆盖。
4. 确认候选不存在可复核的 linux/amd64 纯镜像身份材料，无法验证 OCI revision、Mounts、镜像 secret scan 和关键源码 hash。
5. 生成 Phase 8B Owner 审阅报告与结构化 manifest；最终结论为 `HOLD_WITH_EVIDENCE`。未修改候选代码或提交，未执行 push、merge、deploy、migration、restart、cleanup 或扩流。

---
下一步：你需要操作

第一步：在独立候选中把 Action verification 与可信 RequestContext 或服务端保存/签名的计划绑定，严格校验 actor、workspace、request、capability 和参数。

第二步：补充精确注入、伪造身份、非法参数、歧义实体的安全拒绝与零写入测试，并统一 `proposed/cancelled` 状态和失败时“没有修改你的数据”的文案契约。

第三步：补齐 trace_id、plan_id、capability、脱敏 actor/workspace、最终状态和 failure_code 的端到端审计链。

第四步：全部代码门禁通过后，另行构建候选 backend/frontend linux/amd64 纯镜像并验证 OCI revision、Mounts=[]、镜像秘密扫描和源码 hash，再重新申请 Owner Release Review。
