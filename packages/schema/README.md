# Schema

负责定义原始数据表、标准化数据表和分析结果表。

## 建议的核心表

- `crawl_runs`
- `raw_requests`
- `raw_responses`
- `items`
- `item_snapshots`
- `seller_profiles`
- `daily_metrics`
- `analysis_reports`

## 第一阶段字段原则

- 先保留原始字段
- 再补标准化字段
- 每个结果都要能回溯到原始响应
