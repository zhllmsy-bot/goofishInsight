# Local Runtime SOP

更新时间：2026-04-03
适用项目：仓库根目录（通过 `GOOFISH_ROOT_DIR` 或 `git rev-parse --show-toplevel` 解析）

这是一份本机运行 SOP。

目标只有 5 个：

1. 判断本地大模型是否已启动。
2. 判断本地大模型是否健康。
3. 判断看板是否已启动、是否健康。
4. 判断二次清洗、首页 feed、batch collect 是否已启动、是否健康。
5. 在不乱猜、不乱改的前提下，用最短路径把它们恢复。

这份 SOP 故意写得很死。

照着做，不要自己发明新步骤。

## 0. 固定规则

先进入项目根目录（优先使用 `GOOFISH_ROOT_DIR`）：

```bash
ROOT_DIR="${GOOFISH_ROOT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT_DIR"
```

本机固定值：

- 项目目录：`$ROOT_DIR`
- 本地模型端口：`127.0.0.1:8000`
- 看板端口：`127.0.0.1:8787`
- 附着浏览器 CDP：`http://127.0.0.1:9222`
- 本机优先 profile：`chrome-attached-mac`
- 二次清洗只允许使用本机模型：`http://127.0.0.1:8000/v1`
- 本机模型路径：`$AI_MODEL`（默认指向你本机的 Qwen3 模型目录）

固定禁止事项：

- 不要让二次清洗回落到远端 AI。
- 不要同时跑 `watch-home-feed` 和 `collect-batch`。
- 不要一上来就跑全量任务。
- 先做 smoke，再做正式任务。
- 如果某一步失败，不要继续往下做，先按本 SOP 的 if/then 回退。

## 1. 先理解两个词

这份 SOP 里，两个词必须分开：

- `已启动`：意思是进程或端口现在真的存在。
- `健康`：意思是它不只是“活着”，而是真的能完成自己的最小任务。

例子：

- `8787` 端口开着，只能说明看板“可能已启动”。
- `8787/healthz` 返回 `{"ok":true}`，再加首页能返回 HTML，才叫“健康”。

## 2. 总顺序

永远按这个顺序检查：

1. 大模型
2. 看板
3. 二次清洗
4. 附着浏览器
5. 首页 feed
6. batch collect

原因：

- 二次清洗依赖大模型。
- feed 和 batch collect 依赖附着浏览器。
- 看板虽然不依赖大模型，但它是最容易先看出数据库链路是否卡住的入口。

## 3. 大模型 SOP

### 3.1 判断大模型是否已启动

执行：

```bash
lsof -iTCP:8000 -sTCP:LISTEN -n -P || true
```

IF 有输出
THEN 说明 `8000` 端口上有进程，继续做 `3.2`

IF 没有输出
THEN 说明模型没有启动，直接做 `3.3`

### 3.2 判断大模型是否健康

执行：

```bash
curl -s http://127.0.0.1:8000/v1/models
```

IF 返回内容里包含当前 `AI_MODEL` 对应的模型路径

THEN 说明模型健康，跳到 `4. 看板 SOP`

IF 返回为空
THEN 模型不健康，做 `3.3`

IF 返回的是：

```text
旧的 Qwen2.5 模型
```

THEN 说明端口虽然有服务，但模型错了，做 `3.4`

### 3.3 启动大模型

执行：

```bash
MLX_PYTHON="${MLX_PYTHON:-python3}"
AI_MODEL="${AI_MODEL:-$HOME/ml-models/Qwen3-30B-A3B-MLX-4bit}"
"$MLX_PYTHON" -m mlx_lm server \
  --model "$AI_MODEL" \
  --host 127.0.0.1 \
  --port 8000 \
  --use-default-chat-template \
  --temp 0.0 \
  --max-tokens 1024 \
  --chat-template-args '{"enable_thinking":false}'
```

注意：

- 这是前台命令。
- 看到服务起来以后，不要马上关掉这个终端。

启动后，立刻回到 `3.2`

### 3.4 端口上模型错了，如何修

先检查是不是旧的 `Qwen2.5` 守护进程在抢端口：

```bash
launchctl list | rg 'ecommerce-qwen-api-8000|qwen'
```

IF 看到了：

```text
com.admin.ecommerce-qwen-api-8000
```

THEN 执行：

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.admin.ecommerce-qwen-api-8000.plist
```

然后重新做 `3.3`

IF 没看到这个 label
THEN 直接重新做 `3.1` 和 `3.3`

## 4. 看板 SOP

这里的看板指 `apps/collector` 提供的 FastAPI/Jinja 运维入口（`serve-web`），不是 `apps/dashboard-react` 开发服务器。

### 4.1 判断看板是否已启动

执行：

```bash
lsof -iTCP:8787 -sTCP:LISTEN -n -P || true
```

IF 有输出
THEN 继续做 `4.2`

IF 没有输出
THEN 直接做 `4.3`

### 4.2 判断看板是否健康

先检查健康接口：

```bash
curl -s http://127.0.0.1:8787/healthz
```

IF 返回：

```json
{"ok":true}
```

THEN 再检查首页：

```bash
curl -s http://127.0.0.1:8787/ | sed -n '1,5p'
```

IF 输出前几行里有：

```text
<!DOCTYPE html>
```

THEN 看板健康，跳到 `5. 二次清洗 SOP`

IF `healthz` 不返回，或者首页不返回 HTML
THEN 看板不健康，做 `4.3`

### 4.3 启动看板

执行：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli serve-web --host 127.0.0.1 --port 8787
```

注意：

- 这是前台命令。
- 看到 `Uvicorn running on http://127.0.0.1:8787` 后，不要关掉这个终端。

启动后，立刻回到 `4.2`

## 5. 二次清洗 SOP

### 5.1 判断二次清洗是否“正在运行”

执行：

```bash
ps aux | rg 'review-v3-second-pass|start-review-v3-resident|control-review-v3-direct' | rg -v rg
```

IF 有输出
THEN 说明它“已启动”

IF 没有输出
THEN 说明它“当前没有运行”

注意：

- 二次清洗是短任务。
- 没有进程，不代表它坏了。
- 所以必须继续做 `5.2`

### 5.2 判断二次清洗是否健康

先确认模型健康。

IF `3.2` 没通过
THEN 不要测二次清洗，先回去修模型。

执行 smoke：

```bash
env \
  AI_PROVIDER=openai_compatible \
  AI_BASE_URL=http://127.0.0.1:8000/v1 \
  AI_API_KEY=local-dev \
  AI_MODEL="${AI_MODEL:-$HOME/ml-models/Qwen3-30B-A3B-MLX-4bit}" \
  PYTHONPATH=apps/collector/src \
  ./.venv/bin/python -m goofish_insight.cli review-v3-second-pass \
    --limit 3 \
    --output reports/review-second-pass-qwen3-check-$(date +%Y%m%d-%H%M%S).json
```

IF 输出里出现：

```text
second_pass_chunk_completed
```

THEN 继续检查文件：

```bash
ls -1t reports/review-second-pass-qwen3-check-* | head -n 3
```

IF 能看到：

- 一个 `.json`
- 一个 `.usage.json`
- 一个 `.low-confidence.json`

THEN 二次清洗健康，跳到 `6. 附着浏览器 SOP`

IF 没看到这 3 个文件
THEN 二次清洗不健康，停止，先查当前命令输出

IF 命令里出现连接 `8000` 失败
THEN 回到 `3. 大模型 SOP`

### 5.3 正式启动二次清洗

如果 smoke 成功，再跑稍大一点的任务。

执行：

```bash
PHASE=second_pass LIMIT=10 OUTPUT_PATH=reports/review-v3-second-pass-local-$(date +%Y%m%d-%H%M%S).json ./scripts/start-review-v3.sh
```

IF smoke 没成功
THEN 不允许跑正式任务

## 6. 附着浏览器 SOP

### 6.1 判断附着浏览器是否已启动

执行：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli show-attached-browsers
```

IF 返回 `[]`
THEN 说明附着浏览器没起来，做 `6.2`

IF 返回不是 `[]`
THEN 说明附着浏览器已启动，跳到 `7. 首页 feed SOP`

### 6.2 启动附着浏览器

执行：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python scripts/open_attached_browser.py --profile-key chrome-attached-mac --port 9222
```

IF 输出里出现：

- `"status": "started"`
- 或 `"status": "already_running"`

THEN 回到 `6.1`

IF 报错
THEN 停止，不要继续跑 feed 或 batch collect

## 7. 首页 feed SOP

### 7.1 判断首页 feed 是否“正在运行”

执行：

```bash
ps aux | rg 'watch-home-feed|refresh-home-feed' | rg -v rg
```

IF 有输出
THEN 说明 feed 当前已启动

IF 没有输出
THEN 说明 feed 当前没有运行

注意：

- 有没有进程，不等于健康。
- 还要继续做 `7.2`

### 7.2 判断首页 feed 是否健康

先确认 `6. 附着浏览器 SOP` 已通过。

执行 smoke：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli watch-home-feed \
  --profile-key chrome-attached-mac \
  --max-cycles 1 \
  --dry-run
```

IF 输出是 1 条 JSON 摘要，而且里面包含：

- `visible_card_count`
- `target_match_count`

THEN 首页 feed 健康

IF 输出里出现：

```text
requires an attached Chrome instance with CDP enabled
```

THEN 回到 `6. 附着浏览器 SOP`

IF 不是 JSON 摘要，而是直接报错
THEN 首页 feed 不健康，停止

### 7.3 正式启动首页 feed

只有 smoke 成功后，才允许正式启动：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli watch-home-feed \
  --profile-key chrome-attached-mac \
  --interval-seconds 20 \
  --max-messages 0 \
  --dry-run
```

严格限制：

- 先用 `--dry-run`
- 先用 `--max-messages 0`
- 不允许一上来就发消息

## 8. batch collect SOP

### 8.1 判断 batch collect 是否“正在运行”

执行：

```bash
ps aux | rg 'collect-batch' | rg -v rg
```

IF 有输出
THEN 说明 batch collect 当前已启动

IF 没有输出
THEN 说明 batch collect 当前没有运行

注意：

- 有没有进程，不等于健康。
- 还要继续做 `8.2`

### 8.2 判断 batch collect 是否健康

先确认：

- `6. 附着浏览器 SOP` 已通过
- `7. 首页 feed` 当前没有在跑

执行数据库健康检查：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli show-health
```

如果这个命令本身报数据库错误
THEN 不允许继续跑 batch collect

再执行 smoke：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli collect-batch \
  --config-path reports/smoke-collect-batch-config.json \
  --profile-key chrome-attached \
  --parallel-tabs 1
```

smoke 跑完后，立刻再看一次：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli show-health
```

IF 最新的 run 里有：

- `"status": "completed"`
- `"pages_succeeded":` 大于 `0`

THEN batch collect 健康

IF 最新的 run 里有：

- `"status": "failed"`
- 或 `"pages_succeeded": 0`

THEN batch collect 不健康

### 8.3 正式启动 batch collect

只有 smoke 成功后，才允许跑正式任务：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli collect-batch \
  --config-path apps/collector/configs/monitor_tasks.json \
  --profile-key chrome-attached-mac \
  --parallel-tabs 8
```

严格限制：

- 先 smoke，后正式
- 第一次正式跑之前，先确认首页 feed 没在跑
- 如果怀疑浏览器会抢标签页，先把并发降到 `1`

## 9. 一眼判断表

如果你只想快速判断，按这个表执行。

### 9.1 大模型

执行：

```bash
curl -s http://127.0.0.1:8000/v1/models
```

IF 看到 `Qwen3-30B-A3B`
THEN 正常

IF 没看到
THEN 不正常

### 9.2 看板

执行：

```bash
curl -s http://127.0.0.1:8787/healthz
```

IF 返回 `{"ok":true}`
THEN 基本正常

IF 不返回
THEN 不正常

### 9.3 二次清洗

执行 `5.2` 的 smoke。

IF 出现 `second_pass_chunk_completed`
THEN 正常

IF 没出现
THEN 不正常

### 9.4 首页 feed

执行 `7.2` 的 smoke。

IF 输出 JSON 里有 `visible_card_count`
THEN 正常

IF 没有
THEN 不正常

### 9.5 batch collect

执行 `8.2` 的 smoke 和 `show-health`。

IF 最新 run 是 `completed` 且 `pages_succeeded > 0`
THEN 正常

IF 不是
THEN 不正常

## 10. 最后一句

永远不要跳步骤。

正确顺序是：

`模型 -> 看板 -> 二次清洗 -> 附着浏览器 -> 首页 feed -> batch collect`

前一步没过，后一步不要跑。
