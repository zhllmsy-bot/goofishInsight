# C14 文档叙事与现状对齐

Status: Proposed
Priority: P2

## 目标

把 README、SPEC、模块 README、前端路径文档、Web 文档，统一到当前真实系统形态。

## 为什么现在做

现在最大的问题之一不是没有文档，而是文档比真实代码多讲了一套旧故事。

## 主要问题证据

- 顶层 README 仍大量保留早期叙事：[README.md](<repo-root>/README.md)
- Web README 仍把 `apps/web` 说成主要展示层：[apps/web/README.md](<repo-root>/apps/web/README.md)
- 前端路径文档仍写 Next.js / ECharts / TanStack Table：[04-frontend-path.md](<repo-root>/docs/04-frontend-path.md)

## 范围

1. 明确 React 主工作台、FastAPI 主事实源、Nest BFF 回退层的现状。
2. 标记 legacy 模板与 admin-only 页面。
3. 删除已过期的前端技术叙事。
4. 给每个子模块一条真实职责描述。

## 不做

1. 不扩写新愿景。
2. 不再生成新的大而全路线图文档。

## 建议写文件范围

- [README.md](<repo-root>/README.md)
- [SPEC.md](<repo-root>/SPEC.md)
- [apps/web/README.md](<repo-root>/apps/web/README.md)
- [docs/04-frontend-path.md](<repo-root>/docs/04-frontend-path.md)
- [apps/dashboard-react/README.md](<repo-root>/apps/dashboard-react/README.md)
- [apps/dashboard-nest/README.md](<repo-root>/apps/dashboard-nest/README.md)
- [apps/analyzer/README.md](<repo-root>/apps/analyzer/README.md)

## 验证

1. 文档抽样检查不再出现互相矛盾的前端主入口描述。
2. 文档中的主链路都能指到实际代码入口。

## 完成定义

1. 文档说的系统，和代码里的系统是同一个系统。
2. 不再把旧模板层、旧技术选型、过期愿景写成当前事实。
