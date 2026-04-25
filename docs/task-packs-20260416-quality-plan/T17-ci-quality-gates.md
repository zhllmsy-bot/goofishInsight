# T17 CI 质量门禁与本地脚本规范化

Status: Done
Priority: P1
Source: 仓库缺少 GitHub Actions，现有本地 CI 入口脚本仍带绝对路径与 zsh 绑定
Done At: 2026-04-16

## 目标

把已有的 selected integration、dashboard build、基础测试门禁搬到可重复执行的 CI 工作流，并把本地脚本改成可移植的 Bash 版本。

## 独占文件

- [run_selected_integration.sh](<repo-root>/scripts/ci/run_selected_integration.sh)
- `.github/workflows/quality-gates.yml`（new）
- `scripts/ci/run_dashboard_checks.sh`（new）
- `scripts/ci/run_python_quality.sh`（new）

## 范围

- 将 `run_selected_integration.sh` 改为 `#!/usr/bin/env bash`，移除硬编码仓库绝对路径。
- 新增 GitHub Actions workflow，覆盖：
  - Python selected integration
  - Dashboard React build
  - Dashboard Nest build/test
- 把 CI job 入口拆成更小的本地脚本，方便单独重跑。

## 不做

- 不跑全量 e2e
- 不引入 coverage 上传平台
- 不改 package 依赖版本

## 交付物

- 仓库首次拥有可运行的 GitHub Actions 基础工作流
- 本地与 CI 共用同一套脚本入口
- CI 脚本不依赖开发者本机固定目录

## 验证

```bash
cd <repo-root> && bash scripts/ci/run_selected_integration.sh
cd <repo-root> && bash scripts/ci/run_dashboard_checks.sh
```

## 完成定义

- `.github/workflows/quality-gates.yml` 可以在干净环境运行
- `run_selected_integration.sh` 在非 zsh 下也能执行
- 所有脚本都从当前仓库根目录解析路径
