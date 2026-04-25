# T20 文档与脚本可移植性清理

Status: Done
Priority: P3
Source: 文档与脚本仍有绝对路径、平台绑定 shebang、过时说明
Done At: 2026-04-16

## 目标

清理最容易误导后续维护者的文档与脚本可移植性问题，让运行说明、恢复文档和常用启动脚本更接近“换一台机器也能照着跑”。

## 独占文件

- [README.md](<repo-root>/README.md)
- [14-local-runtime-sop.md](<repo-root>/docs/14-local-runtime-sop.md)
- [P0b-backup-recovery-guide-20260413.md](<repo-root>/docs/P0b-backup-recovery-guide-20260413.md)
- [start-analyzer-resident.sh](<repo-root>/scripts/start-analyzer-resident.sh)
- [start-batch-collect-resident.sh](<repo-root>/scripts/start-batch-collect-resident.sh)

## 范围

- 把绝对路径示例改成变量化或仓库相对写法。
- 为关键 shell 脚本补用途头注释与统一 shebang。
- 更新 README 中 dashboard 运行口径，明确 React/Nest/FastAPI 的当前关系。
- 清理备份恢复文档里容易误用的本机路径示例。

## 不做

- 不改 CI 脚本
- 不改 launchd plist
- 不补整套 CLI 手册

## 交付物

- 常用文档不再依赖作者本机路径
- 常用启动脚本具备统一可读头部
- README 与当前部署拓扑一致

## 验证

```bash
cd <repo-root> && bash -n scripts/start-analyzer-resident.sh
cd <repo-root> && bash -n scripts/start-batch-collect-resident.sh
```

## 完成定义

- README / SOP / 恢复文档里的路径示例可移植
- Shell 脚本具备统一 shebang 与用途说明
- 文档口径不再与当前代码实现冲突
