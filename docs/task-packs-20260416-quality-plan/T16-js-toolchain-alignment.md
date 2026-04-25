# T16 JS 工具链对齐与 React 测试基座

Status: Done
Priority: P1
Source: React 与 Nest 的 TypeScript/Jest 工具链版本和测试基座不一致

## 目标

统一 monorepo 内前端相关 TypeScript 口径，去掉 Nest 的 Jest 30 预发布依赖，并给 React 端补一套最小可用测试基座。

## 独占文件

- [package.json](<repo-root>/package.json)
- [apps/dashboard-react/package.json](<repo-root>/apps/dashboard-react/package.json)
- [apps/dashboard-nest/package.json](<repo-root>/apps/dashboard-nest/package.json)
- [apps/dashboard-react/tsconfig.json](<repo-root>/apps/dashboard-react/tsconfig.json)
- [apps/dashboard-react/tsconfig.app.json](<repo-root>/apps/dashboard-react/tsconfig.app.json)
- [apps/dashboard-react/tsconfig.node.json](<repo-root>/apps/dashboard-react/tsconfig.node.json)
- [apps/dashboard-nest/tsconfig.json](<repo-root>/apps/dashboard-nest/tsconfig.json)
- `apps/dashboard-react/vitest.config.ts`（new）
- `apps/dashboard-react/src/test/setup.ts`（new）
- `apps/dashboard-react/src/test/smoke.test.ts`（new）

## 范围

- 把 React 与 Nest 对齐到同一主版本 TypeScript。
- 将 Nest 的 `jest@30` / `@types/jest@30` 降回稳定版。
- 为 React 端引入 `vitest + jsdom + testing-library` 最小测试基座。
- 在根 workspace 中补充统一的 typecheck/test 脚本入口。

## 不做

- 不新增大规模组件测试
- 不改 `scripts/ci/run_selected_integration.sh`
- 不刷新整个前端依赖栈到最新大版本

## 交付物

- 单一 TypeScript 主版本
- Nest 测试链回到稳定版本
- React 可开始编写单元/RTL 测试

## 验证

```bash
cd <repo-root> && npm ls typescript --all
cd <repo-root>/apps/dashboard-react && npm run build
cd <repo-root>/apps/dashboard-nest && npm test -- --runInBand
```

## 完成定义

- `npm ls typescript --all` 不再出现 React 6 / Nest 5 的双轨主版本
- React 端存在可执行测试入口
- Nest 不再依赖 Jest 30 预发布版本
