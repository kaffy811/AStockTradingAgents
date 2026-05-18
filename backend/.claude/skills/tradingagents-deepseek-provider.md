# Skill: tradingagents-deepseek-provider
你是 TradingAgents 的 LLM 接入工程师。

## DeepSeek 核心信息
Base URL：https://api.deepseek.com
完全兼容 OpenAI Python SDK（只改 base_url 和 api_key）
模型：deepseek-chat（通用）/ deepseek-reasoner（风控主管推理）

## LLM 工厂设计
抽象接口：LLMClient.chat(messages, stream=False) -> str
工厂函数：get_llm_client(provider=None) 读取 settings.LLM_PROVIDER
Provider 实现：DeepSeek / OpenAI / Qwen（只改 base_url + api_key + model）

## 环境变量
LLM_PROVIDER=deepseek / DEEPSEEK_API_KEY / DEEPSEEK_MODEL=deepseek-chat
LLM_TEMPERATURE=0.3 / LLM_MAX_TOKENS=4096

## 错误处理
RateLimitError → 指数退避重试3次（2/4/8s）
AuthenticationError → 立即报错推 SSE error
APIConnectionError → 重试1次后切换备用 Provider
ContentFilterError → 返回固定合规声明文本

## 成本估算
单次完整分析约 15000-20000 tokens（DeepSeek 成本极低）
每个 Agent 设置 max_tokens 上限

## 禁止
不硬编码 API Key / 设置 httpx timeout=60 / 不打印完整响应日志
Provider 切换不影响 Agent 层调用接口
