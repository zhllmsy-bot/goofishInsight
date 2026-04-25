# T4 规则回放与 `price_sanity_score`

Status: Done
Priority: P1
Source Todo: W5 未完成项
Done At: 2026-04-15

## 目标

把规则引擎从“能跑”推进到“可发布”，补齐 `20+20` 回放样本、固定执行顺序、落地历史分位区间版 `price_sanity_score`。

## 独占文件

- [normalizers.py](<repo-root>/apps/collector/src/goofish_insight/normalizers.py)
- [rule_alias_matcher.py](<repo-root>/apps/collector/src/goofish_insight/application/services/rule_alias_matcher.py)
- [rule_aliases.json](<repo-root>/apps/collector/configs/rule_aliases.json)
- [price_sanity_ranges.yaml](<repo-root>/apps/collector/configs/price_sanity_ranges.yaml)
- [run_rule_replay.py](<repo-root>/scripts/rules/run_rule_replay.py)
- [test_rule_alias_matcher.py](<repo-root>/apps/collector/tests/test_rule_alias_matcher.py)
- [test_normalizers.py](<repo-root>/apps/collector/tests/test_normalizers.py)
- [fixtures](<repo-root>/apps/collector/tests/fixtures)

## 范围

- 实现 `exact alias -> contains alias -> template token`
- Apple/Garmin 各补至少 `20` 条 fixture
- 回放报告 JSON 固定落盘到 `reports/rules/`
- 样本 `>=100` 时走历史分位区间，否则回退人工配置

## 交付物

- Apple/Garmin 回放准确率报告
- 权重敏感性分析结果
- 第一批品类可通过配置扩展，且有回放报告兜底

## 完成结果

- 已固定执行顺序：`exact alias -> contains alias -> template token`（template token 仍走 `normalizers.py` 原有回退逻辑）。
- 已补齐 Apple/Garmin 各 `20` 条 JSONL fixture（共 `40` 条）。
- 回放报告已固定落盘到 `reports/rules/`，并维护 `latest-rule-replay-report.json`。
- `price_sanity_score` 已实现：样本数 `>=100` 走历史分位区间，样本不足走 `price_sanity_ranges.yaml` 人工配置兜底。
- 最新报告：
  - `reports/rules/rule-replay-20260415-205828.025264_0800.json`
  - `reports/rules/latest-rule-replay-report.json`

## 验证

```bash
./.venv/bin/python scripts/rules/run_rule_replay.py
PYTHONPATH=apps/collector/src ./.venv/bin/python -m unittest \
  apps.collector.tests.test_rule_alias_matcher \
  apps.collector.tests.test_normalizers
```
