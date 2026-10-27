---
目前完成的工作汇总：

已完成

1. 完成 Phase 7E-P1.3 生产版本一致性与运行资源只读核验
- Git、backend 与 frontend OCI revision 均为 `fdcdc264e9178f7bb432f9101092b08c78af1ee6`，无版本偏差。
- backend、PostgreSQL、Redis 健康；所有容器 restart=0、OOM=false；Swap 未使用。

2. 完成公网 HTTP、服务器内网 Company API 与数据源三侧对照
- 发现公网 `/api/v2` 返回 SPA HTML，而 server-local 同路径返回 JSON 与有效 CNINFO/Tushare 数据。
- 证明 000725 与 600519 裸代码 EOD 可用、非实时且有 source/as_of/unit；带 `.SZ/.SH` 的 EOD 标识未正确归一化。
- 记录 000725 quarterly history 空缺与一次 BaoStock 20 秒 timeout。

3. 完成 Supabase、Redis、CNINFO/RAG 与调度状态盘点
- Supabase/Redis 可用；Redis 32 个 key 全部设置过期。
- 生产库有 302 份报告记录、6 个 Company RAG document、1721 chunks；Report RAG runtime 当前关闭且 embedding 为 mock。
- 未发现应用定时器；coverage snapshot 停留在 2026-07-07，108 项 missing queue pending。

4. 生成只读取证材料
- `backend/docs/artifacts/phase7e_p1_3_production_bug_inventory.md`
- `backend/docs/artifacts/phase7e_p1_3_production_bug_inventory.json`
- `HKNA/docs/suggestion/suggest10.md`

5. 保持禁止边界
- 未修改代码、未 push、未部署、未重启容器、未构建镜像、未 migration、未全量抓取、未清缓存、未扩流。

---
下一步：你需要操作

第一步：先修复 frontend Nginx 的 `/api/v2` 公网反代契约，并增加真实 JSON content-type/body smoke。

第二步：统一 Company EOD 对裸六码和 `.SZ/.SH` 的代码规范化，不改变数据源或数值校验规则。

第三步：连接可用浏览器并使用指定测试账号新建五个会话，补齐截图、Network、console、UI 状态和 request-ID 日志关联；在此之前不能宣称 Chat/UI 线上验收通过。
