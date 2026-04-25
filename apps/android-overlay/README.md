# Goofish Overlay Android App

闲鱼二手商品浮层估价工具。在闲鱼页面上层显示浮层按钮，一键截图后自动走 OCR + VLM 识别，结合后端行情数据给出"是否适合快速收货"的判断。

## 当前能力

| 能力 | 状态 |
|------|------|
| 浮层权限申请与浮层开关 | 已完成 |
| MediaProjection 截屏采集 | 已完成 |
| 中英文 OCR 文字识别（ML Kit） | 已完成 |
| 截图 + OCR 数据发送后端分析 | 已完成 |
| 展示分析结论、价格带、趋势、风险提示 | 已完成 |
| 真机端到端联调（MacBook Pro 14 行情页） | 已完成 |
| Apple 中英混排精确规格匹配 | 待优化 |

## 工程结构

```
apps/android-overlay/
├── app/
│   ├── build.gradle.kts
│   ├── proguard-rules.pro
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/goofish/overlay/
│       │   ├── MainActivity.kt              # 入口 Activity
│       │   ├── analysis/
│       │   │   └── OverlayScreenshotAnalyzer.kt  # OCR + 后端请求
│       │   ├── capture/
│       │   │   ├── OverlayCaptureController.kt   # 状态管理（StateFlow）
│       │   │   └── OverlayCaptureService.kt      # 前台服务：浮层 + 截屏
│       │   └── ui/
│       │       ├── GoofishOverlayApp.kt          # Compose 主界面
│       │       └── theme/                        # Material3 主题
│       └── res/
├── build.gradle.kts
├── gradle/
│   ├── libs.versions.toml                  # 版本目录
│   └── wrapper/
├── gradle.properties
├── gradlew / gradlew.bat
└── settings.gradle.kts
```

## 构建要求

- Android SDK：compileSdk 36，minSdk 29，targetSdk 36
- JDK 17
- Gradle Wrapper（已包含）
- Kotlin 2.2.10 + Compose Compiler Plugin

## 构建

```bash
cd apps/android-overlay
./gradlew assembleDebug
```

Debug APK 产出路径：`app/build/outputs/apk/debug/app-debug.apk`

## 安装到真机

```bash
adb install app/build/outputs/apk/debug/app-debug.apk
```

或通过 Android Studio 直接 Run。

## 使用流程

1. 打开 App → 授予浮层权限（SYSTEM_ALERT_WINDOW）
2. 授予通知权限（Android 13+ 需要 POST_NOTIFICATIONS）
3. 点击"授予截屏权限并启动浮层"→ 系统弹窗确认 MediaProjection
4. 切换到闲鱼 App → 屏幕边缘出现紫色圆形"截"按钮
5. 点击"截"按钮 → 自动截图 → OCR → 发送后端分析
6. 回到 App 查看分析结果（结果页 / 通知栏）

## 后端 API 合同

Android 端调用后端两个接口，后端实现在 `apps/collector` 的 FastAPI 服务中。

### POST /api/mobile-overlay/analyze

截图分析主接口。

**请求体：**

```json
{
  "source_package": "com.taobao.idlefish",
  "captured_at": "2026-04-19T12:00:00Z",
  "screen_width": 1080,
  "screen_height": 2400,
  "screenshot_base64": "data:image/png;base64,...",
  "ocr_lines": [
    {"text": "MacBook Pro 14", "left": 120, "top": 80, "right": 600, "bottom": 130},
    {"text": "¥5800", "left": 120, "top": 140, "right": 300, "bottom": 190}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source_package | string? | 否 | 截图来源包名 |
| captured_at | string? | 否 | 截图时间 ISO 8601 |
| screen_width | int? | 否 | 屏幕宽度 px |
| screen_height | int? | 否 | 屏幕高度 px |
| screenshot_base64 | string? | 否 | 截图 data URL（含前缀）或裸 base64 |
| ocr_lines | array | 否 | OCR 识别行，每行含 text + 可选 left/top/right/bottom |

**响应体：**

```json
{
  "ok": true,
  "source_package": "com.taobao.idlefish",
  "captured_at": "2026-04-19T12:00:00Z",
  "ocr_summary": {
    "line_count": 12,
    "title_candidate": "MacBook Pro 14 M4 16G 512G",
    "ocr_title_candidate": "MacBook Pro 14",
    "title_candidate_source": "vlm",
    "listing_price": 5800.0,
    "price_source_text": "¥5800",
    "text_excerpt": "...",
    "screenshot_supplied": true
  },
  "vlm_summary": {
    "enabled": true,
    "used": true,
    "title_candidate": "MacBook Pro 14 M4 16G 512G",
    "brand_hint": "Apple",
    "business_domain_hint": "apple_m_series",
    "model_hint": "MacBook Pro 14",
    "spec_hint": "M4 / 16G / 512G",
    "price_hint": "5800",
    "confidence": 0.85,
    "reason": "...",
    "model": "...",
    "thinking_enabled": true
  },
  "match": {
    "business_domain": "apple_m_series",
    "domain_label": "Apple M 系列",
    "task_key": "...",
    "task_display_name": "...",
    "title_candidate": "MacBook Pro 14 M4 16G 512G",
    "score": 280.5,
    "pricing": {
      "label": "...",
      "product_label": "MacBook Pro 14",
      "spec_label": "MacBook Pro 14 / M4 / 16G / 512G",
      "safe_buy_price": 5200.0,
      "target_buy_ceiling": 5600.0,
      "fair_price": 6100.0,
      "listing_price": 5800.0,
      "expected_profit_margin_pct": 5.17,
      "price_position": "target",
      "is_actionable": true,
      "sample_confident": true,
      "reliability_tier": "high"
    },
    "trend": {
      "latest_close": 6050.0,
      "latest_range_label": "5800-6300",
      "change_label": "近7日持平",
      "volatility_label": "低波动",
      "day_count": 28,
      "trend_quality_ok": true
    }
  },
  "alternatives": [],
  "decision": {
    "status": "yes",
    "quick_flip_ok": true,
    "summary": "当前标价 ¥5,800 落在目标收货上限 ¥5,600 内，可尝试快速收货。",
    "risk_flags": []
  }
}
```

**decision.status 取值：**

| status | 含义 |
|--------|------|
| strong_yes | 优先收——标价低于安全收货价 |
| yes | 可收——标价低于目标收货上限 |
| watch | 观察——标价低于市场中位但未进目标区 |
| no | 放弃——标价高于目标收货上限 |
| needs_review | 待复核——未匹配到有效行情 |

### GET /api/mobile-overlay/healthz

VLM 运行状态检查。

**响应体：**

```json
{
  "ok": true,
  "vlm": {
    "enabled": true,
    "base_url": "http://127.0.0.1:8020",
    "model": "Qwen2.5-VL-72B-Instruct-4bit-MLX",
    "thinking_enabled": true,
    "queue": {
      "worker_alive": true,
      "pending_jobs": 0,
      "active_job_id": null,
      "active_seconds": null,
      "completed_jobs": 15,
      "failed_jobs": 0
    }
  }
}
```

## 联调

### 远程服务器联调（默认）

App 默认后端地址 `http://web.privateaitool.top:3003`，直接可用。

### 本地联调

1. 启动本地后端：
   ```bash
   python -m goofish_insight.cli serve-web
   ```
2. 手机通过 adb 端口转发：
   ```bash
   adb reverse tcp:8787 tcp:8787
   ```
3. App 设置页将后端地址改为 `http://127.0.0.1:8787`
4. 保存后即可联调

### VLM 模型

后端截图分析默认走本机 VLM 模型（Qwen2.5-VL-72B-Instruct），通过串行队列调用避免并发压垮机器。相关环境变量：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| MOBILE_OVERLAY_VLM_ENABLED | true | 是否启用 VLM 截图识别 |
| MOBILE_OVERLAY_VLM_BASE_URL | http://127.0.0.1:8020 | VLM 模型服务地址 |
| MOBILE_OVERLAY_VLM_MODEL | (本地模型路径) | 模型标识 |
| MOBILE_OVERLAY_VLM_TIMEOUT_SEC | 300 | 单次 VLM 调用超时秒数 |
| MOBILE_OVERLAY_VLM_MAX_OUTPUT_TOKENS | 320 | 最大输出 token 数 |
| MOBILE_OVERLAY_VLM_ENABLE_THINKING | true | 是否开启 thinking 模式 |

## 技术栈

- Kotlin 2.2 + Jetpack Compose + Material3
- ML Kit Text Recognition（中文 + 拉丁文双识别器）
- MediaProjection API 截屏
- 前台服务（foregroundServiceType=mediaProjection）保活浮层
- kotlinx-coroutines-android 异步处理
- 后端 FastAPI + VLM + 定价引擎

## 权限

| 权限 | 用途 |
|------|------|
| INTERNET | 调用后端分析接口 |
| SYSTEM_ALERT_WINDOW | 显示浮层按钮 |
| FOREGROUND_SERVICE | 运行浮层前台服务 |
| FOREGROUND_SERVICE_MEDIA_PROJECTION | 前台服务截屏类型声明 |
| POST_NOTIFICATIONS | Android 13+ 通知权限 |

## 已知限制

1. Apple 搜索结果页里"精确规格"偶尔会从 MacBook Pro 14 漂到更高置信的完整型号（如 M4 / 16G / 512G），不阻塞主流程但需继续优化。
2. VLM 调用走串行队列，单次分析耗时可达到数十秒，取决于模型推理速度。
3. 仅支持 Android 10（API 29）及以上。
