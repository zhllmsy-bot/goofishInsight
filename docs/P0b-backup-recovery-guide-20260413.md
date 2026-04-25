# P0b 执行指南：Migration 前备份与恢复演练

**日期**: 2026-04-13  
**目标**: 在执行 Alembic migration 前，完成备份和恢复演练

## 1. 执行备份

### 前置条件
- PostgreSQL 已安装且 `pg_dump` 在 PATH 中
- 数据库连接信息已配置（通过 `.env` 或环境变量）
- 有足够的磁盘空间存储备份

### 执行备份命令

```bash
ROOT_DIR="${GOOFISH_ROOT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT_DIR"

# 方式 1：使用备份脚本（推荐）
bash scripts/db/backup_pre_migration.sh

# 方式 2：手动执行 pg_dump
# 首先获取数据库连接信息
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://USER:PASSWORD@localhost:5432/goofish_insight}"
export PG_URL="${PG_URL:-postgresql://USER:PASSWORD@localhost:5432/goofish_insight}"

# 执行备份
mkdir -p backups/pre-migration
pg_dump \
  --format=custom \
  --verbose \
  --file "backups/pre-migration/goofish-insight-pre-migration-$(date +%Y%m%d-%H%M%S).dump" \
  "$PG_URL"
```

### 备份输出
- 备份文件位置：`backups/pre-migration/goofish-insight-pre-migration-YYYYMMDD-HHMMSS.dump`
- 备份格式：PostgreSQL custom format（支持并行恢复）
- 备份大小：取决于数据库大小

## 2. 恢复演练

### 恢复到测试数据库

```bash
# 创建测试数据库
createdb goofish_insight_test

# 恢复备份
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql://USER:PASSWORD@localhost:5432/goofish_insight_test}"
pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --dbname "$TEST_DATABASE_URL" \
  "backups/pre-migration/goofish-insight-pre-migration-YYYYMMDD-HHMMSS.dump"
```

### 验证恢复

```bash
# 连接到测试数据库
psql -d goofish_insight_test

# 检查关键表
SELECT COUNT(*) FROM items;
SELECT COUNT(*) FROM crawl_runs;
SELECT COUNT(*) FROM collector_job_run;
SELECT COUNT(*) FROM collector_job_checkpoint;

# 检查索引
SELECT indexname FROM pg_indexes WHERE tablename = 'data_quality_metric';
```

### 恢复成功标准
- [ ] 所有表都能成功恢复
- [ ] 行数与原数据库一致
- [ ] 索引都能成功恢复
- [ ] 外键约束都能成功恢复
- [ ] 恢复耗时 < 5 分钟

## 3. 备份保留策略

- 保留最近 14 天的备份
- 每次 migration 前执行一次备份
- 备份文件命名：`goofish-insight-pre-migration-YYYYMMDD-HHMMSS.dump`

## 4. 回滚步骤

如果 migration 失败，执行以下步骤：

```bash
# 1. 停止所有应用进程
launchctl stop com.admin.goofish-batch-collect
launchctl stop com.admin.goofish-review-v3-resident

# 2. 恢复备份
pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --dbname "${PG_URL:-postgresql://USER:PASSWORD@localhost:5432/goofish_insight}" \
  "backups/pre-migration/goofish-insight-pre-migration-YYYYMMDD-HHMMSS.dump"

# 3. 验证恢复
psql "${PG_URL:-postgresql://USER:PASSWORD@localhost:5432/goofish_insight}" -c "SELECT COUNT(*) FROM items;"

# 4. 重启应用
launchctl start com.admin.goofish-batch-collect
launchctl start com.admin.goofish-review-v3-resident
```

## 5. 执行记录

### 备份执行记录
- [ ] 备份时间：_______________
- [ ] 备份文件：_______________
- [ ] 备份大小：_______________
- [ ] 备份耗时：_______________

### 恢复演练记录
- [ ] 恢复时间：_______________
- [ ] 恢复耗时：_______________
- [ ] 验证结果：通过 / 失败
- [ ] 问题描述：_______________

## 6. 注意事项

1. **备份前**：确保没有正在运行的采集任务
2. **备份期间**：不要修改数据库
3. **恢复演练**：使用测试数据库，不要在生产数据库上演练
4. **备份文件**：妥善保管，不要删除
5. **权限**：确保有足够的权限执行 pg_dump 和 pg_restore

## 7. 下一步

完成备份和恢复演练后：
1. 记录备份和恢复的结果
2. 执行 Alembic migration：`alembic upgrade head`
3. 验证 migration 成功
4. 在 runtime.html 中添加指标展示
5. 为 launchd 作业增加健康探针
