# Phase 7C2 Chat Research 状态 UI 运行验收

## 执行结论

Candidate 的前端状态适配、回归测试和生产构建均通过。本次使用本地构造的后端响应契约做只读验收，未请求后端 Provider，因此 AKShare、Eastmoney、Sina、Tencent 调用均为零。

## 五种响应矩阵

| 场景 | 输入状态 | 标题/勾选 | 来源区 | 重试 | 结果 |
|---|---|---|---|---|---|
| CNINFO 官方公告研究 | `fulfilled` | 已完成研究/显示勾选 | CNINFO 公开名称、安全官方 URL、as_of、覆盖、限制 | 不显示 | 通过 |
| Tushare EOD 个股研究 | `partial` | 部分完成/不显示勾选 | 显示为“已授权行情数据”，不暴露内部 adapter/provider 名 | 显示 | 通过 |
| 行业新闻已批准源不足 | `unavailable / NO_APPROVED_INDUSTRY_NEWS_SOURCE` | 当前缺少所需数据/不显示勾选 | 仅“未获得可验证来源” | 不显示 | 通过 |
| Provider 执行超时 | `failed / PROVIDER_NETWORK_TIMEOUT` | 研究执行失败/不显示勾选 | 仅“未获得可验证来源” | 显示 | 通过 |
| 不完整市场概览 | `partial` | 部分完成/不显示勾选 | 展示已验证覆盖和缺失项 | 显示 | 通过 |

## 命令与结果

```text
cd frontend && npm test
67 test files passed
756 tests passed
```

```text
cd frontend && npm run build
971 modules transformed
build passed
```

`npm test -- --runInBand` 首次尝试因 Vitest 4 不支持该 Jest 选项而未执行测试；随后使用项目标准 `npm test` 完整通过。构建仅有既有的 Vite CJS deprecation 与 chunk size 警告，无构建错误。

## 安全校验

- 测试显式向适配器传入内部字段和假值，验证输出不包含它们。
- 视图不直接渲染 raw metadata，组件只接收 Adapter 的白名单输出。
- 未进行 live 抓取、未使用未批准 Provider、未修改后端或数据库。
