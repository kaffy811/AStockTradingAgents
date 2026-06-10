# TradingAgents — 面试问答要点

**用途：** 技术面试、项目介绍、作品集答辩  
**版本：** MVP v0.7，2026-05-29  
**格式：** 预想问题 + 核心回答要点（口语化，可直接练习）

---

## 一、项目整体介绍

### Q: 能先介绍一下这个项目是做什么的吗？

> 这是一个 AI 股票分析平台，核心思路是：用户输入一个股票代码，系统同时从技术面、基本面、同行对比、新闻四个维度调用 LLM 生成分析报告，然后整合成一份综合报告。
>
> 我觉得有几个点比较有技术含量。第一个是多 Agent 并行，四个 Agent 各自调 LLM，串行的话要 120 秒，我用 asyncio.gather 做了并行化，降到了 35–45 秒。第二个是数据稳定性，上游 AkShare、yfinance 这些接口不稳定，我做了 fallback 链加三层 Redis 缓存，热点数据命中速度提升了几百到几万倍。第三个是行业数据，为了让同行对比覆盖更多股票，我把申万一级行业的 5000 多只 A 股全量导入了数据库，用 Hot Score 做动态同行发现。

---

## 二、多 Agent 架构

### Q: 为什么要用多个 Agent，而不是直接一个大 prompt？

> 主要是两个原因。第一，不同维度对 LLM 的输入格式和输出规范要求差异很大——技术面 Agent 需要喂给 LLM 数值指标（MA、RSI、MACD），然后让 LLM 判断趋势；基本面 Agent 需要声明字段边界，因为 PE/ROE 这些数据本身是残缺的，不能让 LLM 用残缺数据生成完整结论。如果塞到同一个 prompt 里，系统提示会非常复杂，且不同规则容易互相干扰。
>
> 第二，独立 Agent 可以独立测试和降级。某个 Agent 失败时其他维度仍然正常输出，用户还是能看到综合报告，只是某个维度显示"failed"状态。

### Q: 并行化是怎么做的？遇到什么问题？

> 因为 FundamentalDataService 这些是同步代码（历史遗留），不能直接 await，所以我用 `asyncio.to_thread` 包装同步 Agent，再用 `asyncio.gather` 并发执行。技术面、基本面、新闻三个是同步包装的，同行对比本身是 async 的，所以直接 await。
>
> 遇到的主要问题是 Redis 的事件循环桥接。Redis 客户端是纯 async 的，但同步代码运行在 to_thread 里，没有 event loop。我写了一个 `sync_get_json` 方法，通过 `asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=2)` 来桥接。这里要注意 `_loop` 不能是 None、不能是 closed、也不能不是 running，三个条件都要检查，否则会在边界情况（比如应用刚启动还没注入 loop）时静默失败。

---

## 三、数据源与缓存

### Q: 为什么不直接用实时行业数据搜索，而是把申万行业分类存到数据库里？

> 我最开始也是想用在线接口的。但实际测试下来，主要的三条路都堵死了：
>
> 1. AkShare 的 `sw_index_third_cons` 接口在我本地测试时列数 mismatch，解析失败
> 2. legulegu.com（AkShare 依赖的底层数据源）504 超时
> 3. EastMoney 接口在代理环境下 ProxyError
>
> 后来发现申万宏源研究自己有一个官方 JSON API，可以直接请求成分股，不依赖任何代理，返回格式是标准 JSON。我就用这个，遍历 31 个行业代码，一次请求一个行业，把结果存到本地数据库。这样每次分析请求只需要查本地数据库，0 网络依赖。
>
> 代价是需要定期刷新（Hot Score 快照），但对于动态同行发现这个场景来说，用"昨天的行业热门股"做同行，比"接口随机失败"要好得多。

### Q: Redis 缓存如果不可用了怎么处理？

> 我设计了五层降级链：Redis → 进程内内存缓存 → 实时打上游 → stale cache（上次成功的旧数据）→ 空列表/降级响应。
>
> 具体做法是 `sync_*` 系列方法在任何异常情况下（loop 为 None、loop 已关闭、Redis 连接失败）都静默返回 None 或 False，不抛异常。上层代码收到 None 就当作 cache miss 继续往下走，和 Redis 根本没有的情况完全一样。
>
> 实测验证：杀掉 Redis 进程，所有 API 仍然 HTTP 200，响应结构零变化，用户感知不到 Redis 是否存在。

### Q: negative cache 是什么，为什么要做这个？

> AkShare 和 yfinance 在连续请求时经常触发 rate limit（429）或者 RemoteDisconnected。如果不做 negative cache，每次请求都会先尝试这两个 provider，等它们失败了再 fallback，平均浪费 2–5 秒在注定失败的请求上。
>
> Negative cache 的思路是：一旦某个 provider 失败，就在 Redis 里写一个标记键（TTL 300–600 秒）。下次请求进来先检查这个键，如果存在就直接跳过这个 provider，不发网络请求。这样失败期间的请求速度会显著提升（测试中从 10.6s 降到 2.3s）。

---

## 四、数据库设计

### Q: 为什么报告用 JSONB 存储，而不是多表规范化？

> 主要考虑了两点。
>
> 第一，报告的"sections"和"agents"字段是按 Agent 动态构建的，结构不固定——如果某个 Agent 失败了，那个 key 可能就是 null 或者有 error 字段。用多表存储意味着每次 Agent 增减都要改表结构。JSONB 直接存 dict，结构变化零迁移成本。
>
> 第二，查询场景主要是按 user_id + market + symbol 筛选，然后拿整份报告渲染，很少需要跨报告聚合某个子字段。所以 JSONB 的查询性能完全够用。
>
> 代价是 JSONB 内部的字段变了不会有编译期检查，只能靠 Pydantic schema 在写入时验证。这个我用 Pydantic model 兜住了。

### Q: watchlist 表的前导零问题是怎么处理的？

> 这是个容易踩坑的细节。A 股代码有前导零（000001、000977 这类），如果在 Pydantic validator 里做 `.strip().upper()` 的同时顺手转了类型（比如转 int），前导零就丢了。
>
> 我的策略是：`market` validator 只做 `.upper()`（强制大写），`symbol` validator 只做 `.strip()`（去掉意外空格），绝对不转型。数据库用 `VARCHAR(32)` 而不是 INT 存储。Python dict 的 join key 是字符串 `"000001"` 精确匹配，而不是数字 `1`。这样从用户输入到 DB 存储到 API 返回到前端显示，全链路不丢前导零。

### Q: 为什么不用 Alembic 做数据库迁移？

> 当前阶段所有的表都是新增的，没有对已有表做列级修改，所以 `create_all` 在启动时自动建表就够用了。`create_all` 是幂等的（表已存在时跳过），开发迭代很方便。
>
> Alembic 的价值主要在于"对已有表的增删列"要有可逆的 migration 脚本，避免生产环境手动 ALTER TABLE 出错。我把这个作为技术债列着——一旦需要修改已有表结构（比如给 watchlist_items 加新列），就引入 Alembic。现在提前引入反而增加认知负担。

---

## 五、前端工程化

### Q: 为什么要从 index.html 单文件迁移，而不是继续在单文件上加功能？

> 核心驱动力是安全问题。系统需要渲染 LLM 返回的 Markdown，而 CDN 版本的 DOMPurify 不满足要求——要用完整版 npm 包才能保证 XSS 防护效果。npm 包只有在有构建工具的项目里才能正确 bundling。
>
> 顺手解决的问题有：全局 CSS（markdown.css 在 scoped 组件里对 v-html 内容无效，必须全局引入）、状态管理（Pinia 在单文件里能跑但引入成本高）、路由（后续历史报告、自选股都需要多路由）。

### Q: keep-alive 下路由参数联动是怎么处理的？

> ComprehensiveAnalysisView 被 `<keep-alive>` 缓存后，路由切换不会重新 setup 组件——这意味着如果在 `onMounted` 里读 route.query，从自选股点"分析"跳转时，`onMounted` 不会再触发，表单不会自动填入。
>
> 解决方案是改用 `watch(() => route.query)` 监听 query 对象变化。同时 `StockInputPanel` 需要接收 `initialMarket` 和 `initialSymbol` props，内部也用 `watch(props)` 同步 form 状态。这样即使组件实例被缓存，query 变化仍然能触发表单更新。

---

## 六、权限与安全

### Q: 用户数据隔离是怎么做的？

> 核心原则：`user_id` 永远从 JWT 读取，永远不从请求体接受。
>
> 后端有一个 `get_current_user` 依赖（FastAPI Depends），解码 JWT 返回 `User` 对象。所有需要鉴权的接口都 `Depends(get_current_user)`，然后用 `user.id` 做查询条件。
>
> PATCH 和 DELETE 接口的查询条件是 `WHERE id = {item_id} AND user_id = {user.id}`，而不是只用 item_id。这样如果有人用别人的 item_id 发请求，查出来是 None，返回 404。从攻击者角度看，它和"这个 ID 根本不存在"没有区别，没有信息泄漏。
>
> 报告历史的 ROW_NUMBER 子查询里也有 `WHERE user_id == user.id`，确保 Python join 用的数据绝对不包含其他用户的报告。

### Q: 前端是怎么做登录鉴权的？

> Pinia auth store 管理 token 和当前用户信息。`baseFetch` 在每个请求头自动注入 `Authorization: Bearer {token}`，收到 401 时自动调用 `logout()` 清空 store 并跳转登录页。
>
> 路由守卫（`beforeEach`）检查 `authStore.token`，未登录时重定向到登录页。这样不管从哪个 URL 直接访问，都会被守卫拦住。

---

## 七、LLM 工程

### Q: 怎么防止 LLM 生成误导性结论？

> 分三层约束。
>
> 第一层，Agent 级别：每个 Agent 的系统提示里都有对应的措辞约束。比如 TechnicalAnalystAgent 的提示里写明"没有均线交叉信号时禁止写'金叉'/'死叉'"；NewsAnalystAgent 的提示里有禁止词汇列表（"利好"、"利空"、"将推动上涨"等），并要求附带免责声明。
>
> 第二层，综合报告级别：`ComprehensiveAnalysisCoordinator` 的系统提示有 11 条规则，其中规则 7 明确要求"综合摘要只能整合子报告的事实，不得新增断言，不得放大局部结论"，规则 11 列出强烈措辞（"多重压力叠加"、"极为稳健"）和中性替代表达。
>
> 第三层，字段边界声明：FundamentalAnalystAgent 的提示要求 LLM 在报告中主动声明"以下分析基于可获取的有限字段，不构成完整基本面判断"。
>
> 效果：经过多轮测试，过强措辞基本消除。这个方法的局限是依赖 LLM 遵守指令，无法做到 100% 约束——所以我设计了 warning 系统，在前端用黄色徽章标注"港股基本面有限"、"同行数据不可用"等情况，给用户足够的信息判断报告可靠性。

---

## 八、LangGraph 与 Agent 框架

### Q: 你这个项目用了 LangGraph 吗？

> 目前没有。当前使用的是**自定义多 Agent Coordinator**，通过 `asyncio.gather + asyncio.to_thread` 并发调度四类分析 Agent（技术面、基本面、同行对比、新闻），不依赖任何 Agent 框架。
>
> LangGraph 是下一阶段计划引入的工作流框架。我目前对它的理解是：它把 Agent 的执行过程建模为一个有向图（`StateGraph`），每个 Agent 是一个 Node，Agent 之间的数据传递是 Edge，可以根据中间状态做条件跳转（Conditional Edge），并通过 Checkpoint 实现状态持久化和断点恢复。这些是当前自定义 Coordinator 做不到或做起来代价很高的事情。

### Q: 为什么现在不用 LangGraph，而要等到后续？

> 主要是复杂度匹配的问题。MVP 阶段的核心流程是"4 个 Agent 全部跑完，然后出综合报告"，这是一个固定拓扑，没有条件分支、没有循环、没有中途等待用户确认的需求。这种情况下自定义 Coordinator 的代价很低，调试起来也更直接——出错了看 Python 栈就够了。
>
> LangGraph 的价值在于"状态驱动的 Agent 工作流"：技术面结论出来之后，根据信号强弱动态决定是否触发加深分析；基本面数据质量极差时暂停等用户确认（Human-in-the-loop）；LLM 超时后从最后一个成功的 Node 断点续跑。这些需求目前还没有，等产品逻辑复杂到这一步再引入，引入成本反而更低。

### Q: 如果要引入 LangGraph，你的迁移策略是什么？

> 不直接替换当前接口，而是新增一个 `POST /api/v1/analysis/comprehensive-v2` 接口，跑 LangGraph 版本的 StateGraph。旧的 `/comprehensive` 接口保留不动，前端流量分阶段切换。
>
> 具体步骤：先把 4 个 Agent 包装成 LangGraph Node，State 用 TypedDict 定义；然后加 Checkpoint 验证断点恢复；再加第一个 Conditional Edge（技术面信号 → 是否加深）。等新接口在测试中稳定之后，再逐步把流量从旧接口迁移过去。
>
> 这样的好处是：新旧两个接口可以并行跑对比实验，回归验证更安全；万一 LangGraph 版本有问题，前端直接切回旧接口，不影响用户。

---

## 九、如果让你重来

### Q: 如果重新做这个项目，哪里会做得不一样？

> 有两点。
>
> 第一，申万行业接口的问题应该更早做离线数据探针。Phase 0 测试时我只测了能不能请求到数据，没有测解析逻辑。如果早点用真实数据跑一遍 parse，列数 mismatch 的问题会在 Phase 1A 之前就发现，可以直接选官方 JSON API，节省几次无效尝试。
>
> 第二，应该更早引入 Alembic。我现在把它列为"有需要时再引入"，但其实在项目有 5 张表的时候，schema 的演进已经够复杂了。如果后续需要给 watchlist_items 加列（比如 tags 字段），手动 ALTER TABLE 很容易出错。早引入 Alembic 的边际成本比晚引入要低很多。

---

*文档更新于 2026-05-29*
