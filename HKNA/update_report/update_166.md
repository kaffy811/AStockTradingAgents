---
目前完成的工作汇总：

已完成

1. Phase 7E-P1.9 EOD 金融数值展示归一化
- 新增独立 backend 展示投影模块，仅处理已验证 EOD evidence 的中文单位与两位小数格式。
- 使用 Decimal 与 ROUND_HALF_UP 确定性换算价格、比率、估值倍数、成交额、市值和成交量；不使用 LLM 换算。
- 完整保留 canonical value/unit、source、as_of、report_period 和 evidence ID，并新增 display value/unit 与 rounding policy。

2. 安全降级与数值证据
- 未知或错误单位不转换、不展示原始数字，并返回受控 partial/unavailable。
- 错误舍入和错误数量级无法通过既有 request-level numeric validator；未修改 validator 实现或严格性。
- 成交量仅按手/万手展示，不转换为股；7,616,584.07 手按数学定义显示为 761.66 万手。

3. 测试与构建
- 三条个股 fixture 均保持 fulfilled、numeric validation valid、unsupported tokens 为空，LLM 与未批准 Provider 调用为 0。
- 后端相关测试 108 项、前端定向 24 项、完整前端 769 项通过，production build 通过。
- 本阶段未调用 live Provider，未修改 Provider、缓存、路由、数据库、Docker、依赖、Token、migration 或新闻能力。

---
下一步：你需要操作

第一步：Owner 只读审阅显示单位映射、舍入规则、负向测试和候选 diff。
第二步：审阅通过后再单独授权 merge、push 和部署；本阶段禁止这些操作。
第三步：部署后用单次受控生产 smoke 核验中文展示，不重复调用或绕开正常缓存。
