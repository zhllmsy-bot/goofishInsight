# T18 packages/utils 去留决策与 ESM 化

Status: Done
Priority: P3
Source: `packages/utils` 当前未被仓库引用，且仍是旧式 CommonJS 形态
Done At: 2026-04-16

## 目标

给 `packages/utils` 一个明确去向：要么正式保留并迁移到 ESM + 真测试，要么沉淀退役结论，避免继续作为“看起来存在但没人用”的幽灵包。

## 独占文件

- [packages/utils/package.json](<repo-root>/packages/utils/package.json)
- [packages/utils/tsconfig.json](<repo-root>/packages/utils/tsconfig.json)
- [packages/utils/src/index.ts](<repo-root>/packages/utils/src/index.ts)
- [packages/utils/src/test.ts](<repo-root>/packages/utils/src/test.ts)
- [packages/utils/src/examples.ts](<repo-root>/packages/utils/src/examples.ts)
- [packages/utils/README.md](<repo-root>/packages/utils/README.md)
- [packages/utils/MODULE.md](<repo-root>/packages/utils/MODULE.md)

## 范围

- 明确保留/退役决策，并写进 README/MODULE。
- 如果保留：
  - 迁移到 ESM
  - 把 `src/test.ts` 从 console demo 改成真实测试入口
  - 整理 examples 与 API 说明
- 如果退役：
  - 在包内写清替代方案与迁移路径
  - 避免误导后续开发者继续新增依赖

## 不做

- 不改 root workspace 配置
- 不在本任务里把该包接入 Dashboard 或 Collector
- 不触碰非 `packages/utils/**` 文件

## 交付物

- 一个明确的包生命周期决定
- 包内文档与实现状态一致
- 不再存在“测试文件只是打印日志”的假象

## 验证

```bash
cd <repo-root>/packages/utils && npm run build
```

## 完成定义

- 包状态在 README 中一眼可见
- 文档明确标注为退役的兼容包
- `src/test.ts` 变成可运行的 smoke check
