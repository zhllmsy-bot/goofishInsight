# C13 Monorepo 工具链统一

Status: Done
Priority: P2

## 目标

统一仓库在 npm / pnpm / build / typecheck / test 上的真实口径，消除“能跑但让人困惑”的工具链噪音。

## 为什么现在做

当前顶层是 npm workspaces，但 `pnpm typecheck` 会给出 workspace 警告；这类问题虽然不阻塞功能，但会持续降低协作效率。

## 主要问题证据

- 顶层仅有 `package.json` workspaces：[package.json](<repo-root>/package.json)
- 无 `pnpm-workspace.yaml`

## 范围

1. 明确仓库主 JS 包管理器。
2. 如保留 pnpm 命令，则补齐 workspace 配置。
3. 统一 README / CI / 脚本中的调用口径。

## 不做

1. 不重构前端代码。

## 建议写文件范围

- [package.json](<repo-root>/package.json)
- `pnpm-workspace.yaml`（new, if needed）
- 相关 CI / README

## 验证

```bash
npm run typecheck
npm run test
pnpm typecheck
```

## 完成定义

1. 工具链只有一套明确说法。
2. 文档、CI、本地运行命令不再互相打架。
