# Data Agent 数据层职责说明

本层不调用 LLM，仅做确定性数据整理。

职责：
1. 从财务工具层获取股票各维度财报数据
2. 数据压缩：只保留最近 5-8 期核心指标
3. 生成结构化 compressed_facts（事实列表）
4. 计算数据质量评分（data_quality.score）
5. 记录缺失模块（missing_modules）

数据事实格式：
{
  "fact_id": "{module_key}_{序号三位}",
  "module_key": "growth",
  "metric": "revenue_yoy_pct",
  "value": 12.3,
  "period": "20231231",
  "text": "2023 年营收同比增长 12.3%"
}

禁止行为：
- 不得生成投资观点
- 不得生成买卖建议
- text 只描述客观事实
