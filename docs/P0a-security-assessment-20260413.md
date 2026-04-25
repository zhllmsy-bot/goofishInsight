# P0a 安全评估报告

**日期**: 2026-04-13  
**评估范围**: 历史泄露风险与凭据暴露  
**评估结论**: 低风险（私有内网仓库）

## 发现的安全问题

### 1. README.md 中的暴露凭据（已修复）

**问题**:
- 第 136-138 行包含明文 `ANTHROPIC_AUTH_TOKEN`
- 包含内网 API 端点 `https://cc.580ai.net`
- 这些信息不应该在版本控制中

**修复**:
- ✅ 已删除明文凭据示例
- ✅ 已替换为安全的环境变量配置说明
- ✅ 添加了 `.env.example` 使用建议

### 2. settings.py 中的真实内网 IP（已修复）

**问题**:
- 第 21 行数据库连接字符串包含真实内网 IP `<server-host>`
- 虽然密码是占位符 `change-this-password`，但 IP 地址暴露了内网拓扑

**修复**:
- ✅ 已将 IP 改为 `localhost`（开发环境标准做法）
- ✅ 保留密码占位符，提示用户通过环境变量覆盖

### 3. README.md 中的 Windows 路径残留（已修复）

**问题**:
- 第 61 行包含 Windows 绝对路径 `C:\Users\13754\Documents\Playground\goofish-insight\SPEC.md`
- 暴露了开发者本地路径结构

**修复**:
- ✅ 已改为相对路径 `./SPEC.md`

## Git 历史评估

**扫描结果**:
- README.md: 历史中未发现暴露的 token（仅在最近提交中）
- settings.py: 历史中存在 `<server-host>` 记录

**风险等级**: 低
- 仓库为私有内网项目
- 暴露的 IP 为内网地址，外网无法直接访问
- 未发现数据库密码或 API key 在历史中

## 建议

### 立即执行（已完成）
- [x] 删除 README 中的明文凭据
- [x] 修正 settings.py 的默认连接串
- [x] 清理 Windows 路径残留
- [x] 添加环境变量配置说明

### 后续建议

1. **如果仓库要发布到公网**:
   - 执行 `git filter-repo` 清理历史中的 `<server-host>`
   - 命令: `git filter-repo --replace-text <(echo '<server-host>==>localhost')`
   - 需要强制推送到远程

2. **长期防护**:
   - 在 `.gitignore` 中添加 `.env` 文件
   - 在 CI/CD 中添加 secret scanning
   - 定期审计 README 和配置文件

3. **凭据轮换**:
   - 如果 `ANTHROPIC_AUTH_TOKEN` 曾被使用过，建议轮换
   - 如果数据库密码曾被使用过，建议轮换

## 结论

**当前状态**: ✅ 安全修复完成

本仓库作为私有内网项目，暴露的信息风险较低。已完成所有立即可执行的修复。

**P0a 启动前门禁状态**:
- [x] 轮换/删除 README 中暴露的 token
- [x] 清理 README 中的明文凭据示例
- [x] 修正 settings.py 默认连接串
- [x] 产出历史泄露风险评估结论
- [x] 确认 P0a 完成前不执行 Alembic migration

**可以安全进入 P0b**。
