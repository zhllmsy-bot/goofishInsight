# C12 Android Overlay 工程可交付化

Status: Done
Priority: P1

## 目标

把 `apps/android-overlay` 从“有工程骨架”推进到“可构建、可联调、可说明”的交付状态。

## 为什么现在做

仓库里已经存在 Android overlay 工程，但没有被纳入整体产品收口路线，会长期处于“有代码但没人敢碰”的状态。

## 范围

1. 清点 Android overlay 当前真实能力。
2. 补 README / 联调说明 / 构建说明。
3. 明确与 `/api/mobile-overlay/*` 的合同。
4. 至少保证本地构建口径明确。

## 不做

1. 不新增复杂端侧功能。
2. 不做发布到商店。

## 建议写文件范围

- `apps/android-overlay/**`
- 相关 docs

## 验证

```bash
cd <repo-root>/apps/android-overlay && ./gradlew assembleDebug
```

## 完成定义

1. Android overlay 的交付状态可被单独判断。
2. 后端接口与端侧行为之间有明确合同。
