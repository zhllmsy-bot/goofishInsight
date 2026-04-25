# C11 Mobile Overlay 接入主工作台

Status: Proposed
Priority: P1

## 目标

把 mobile overlay 分析能力接入主 React 工作台，而不是只停留在独立 API。

## 为什么现在做

移动端辅助采集已经有后端能力，但在主运营面里几乎不可见，导致系统能力和产品面脱节。

## 主要问题证据

- API 已存在：[mobile_overlay.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/mobile_overlay.py)
- 主前端没有对应工作区入口：`apps/dashboard-react/src/features/**` 中无 overlay 页面

## 范围

1. 在 React 中新增 overlay 分析入口页。
2. 展示 overlay healthz、最近分析结果、任务匹配结果。
3. 明确它是辅助面，不挤占主 dashboard。

## 不做

1. 不开发手机端 App 功能。
2. 不重写 overlay OCR / VLM 算法。

## 建议写文件范围

- `apps/dashboard-react/src/features/mobile-overlay/**`（new）
- [mobile_overlay.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/mobile_overlay.py)
- [App.tsx](<repo-root>/apps/dashboard-react/src/app/App.tsx)

## 验证

```bash
npm run test -w @goofish/dashboard-react
PYTHONPATH=apps/collector/src:apps/analyzer/src ./.venv/bin/python -m unittest apps.collector.tests.test_mobile_overlay_entrypoints
```

## 完成定义

1. overlay 能力在主工作台可见、可用、可解释。
2. 不再只是“有 API，但产品面上不存在”。
