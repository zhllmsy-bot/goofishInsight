# Android 浮层估价 App TODO

## 目标

在当前 `goofish-insight` 项目内新增一个 Android Studio 兼容的独立 Android 工程，实现：

1. App 可以开启浮层。
2. 进入闲鱼后，点击浮层即可截取当前屏幕。
3. 截图内容被解析成商品关键信息。
4. 结合本项目数据库中的行情趋势、安全收货价、利润空间等指标，判断是否适合快速收货。
5. 结果可以在手机端直接看到。
6. 交互方向对齐 `xianyu_price` 的核心能力，但不由本应用主动唤起目标应用。

## 当前规划

- [x] 在仓库内新增一个 Android Studio 兼容的空白项目。
- [x] 验证 Android 工程可构建、可安装到已连接手机。
- [x] 实现浮层权限申请与浮层开关。
- [x] 实现截屏权限申请与单次截图采集。
- [x] 实现截图后的 OCR / 文本提取链路。
- [x] 在后端新增“截图分析”接口。
- [x] 后端完成商品参数提取、品类识别、趋势查询、安全收货价判断。
- [x] Android 端展示“是否可快速收货”的结论、参考价带和风险说明。
- [x] 完成真机联调。
- [ ] 优化 Apple 中英混排标题下的精确规格命中率（当前已能识别到 MacBook Pro 14 系列，但细到 M1 Pro / M4 仍可能漂移）。

## 技术路线

### Android

- 目录：`apps/android-overlay/`
- 工程形态：Android Studio Blank Project / Gradle Wrapper / Kotlin / Compose
- 能力：
  - `SYSTEM_ALERT_WINDOW` 浮层
  - `MediaProjection` 截屏
  - 前台服务保活浮层
  - OCR 后将文本和截图元信息发送给后端
  - 默认后端地址使用 `.4` 服务器域名 `http://web.privateaitool.top:3003`

### Backend

- 继续复用当前 `apps/collector` 的 FastAPI 服务
- 新增截图分析接口，例如：
  - `POST /api/mobile-overlay/analyze`
- 截图分析默认走本机 `Qwen2.5-VL-72B-Instruct`
- 服务端维护单消费者队列，串行调用 72B，并开启 `thinking`
- 优先复用：
  - 规格提取
  - 定价视图
  - 行情看板 / mobile market 聚合

## 分步验收

### 第 1 步：空白项目

验收标准：

- 仓库内出现独立 Android 工程。
- Android Studio 可以直接打开。
- `./gradlew :app:assembleDebug` 可以通过。

### 第 2 步：浮层 + 截屏

验收标准：

- 手机可授权浮层权限。
- 浮层按钮可显示在闲鱼上层。
- 点击浮层可以完成一次截图并拿到图片文件。

### 第 3 步：分析接口

验收标准：

- 后端可以接收截图分析请求。
- 能输出：
  - 识别出的商品标题 / 型号 / 配置 / 价格
  - 匹配到的业务域
  - 趋势结论
  - 安全收货价
  - 是否适合快速收货

### 第 4 步：端到端

验收标准：

- 手机点击浮层后，几秒内拿到结论。
- 对至少一个真实闲鱼页面跑通。

## 自检循环规则

每完成一个 TODO 后都执行：

1. 自检本步验收标准是否达成。
2. 若未达成，补充缺口并更新本文件。
3. 若达成，标记完成并进入下一步。
4. 如果中途发现路线不合理，重写后续 TODO，但保持目标不变。

## 当前状态

- 状态：端到端闭环已打通，开始进入识别精度优化阶段
- 已完成：
  - `apps/android-overlay/` 空白工程已创建
  - `./gradlew :app:assembleDebug` 已通过
  - debug APK 已安装到已连接手机
  - App 首页已成功拉起
  - 已完成浮层权限授权与前台浮层服务拉起
  - 已在闲鱼页面上层显示圆形浮层按钮
  - 点击浮层按钮后已生成本地截图文件
  - Android 端已完成截图后 OCR，并把文字、位置和 `screenshot_base64` 真图发给后端
  - FastAPI 已提供 `POST /api/mobile-overlay/analyze`
  - `GET /api/mobile-overlay/healthz` 已可查看当前 72B、thinking 和队列状态
  - 截图分析默认接本机 `72B VLM`，并通过服务端串行队列执行，避免并发压垮机器
  - 手机端已展示分析结论、价格带、趋势和风险提示
  - 已在真实闲鱼 `macbookpro14` 行情页完成一轮端到端联调
  - 已移除“打开 xianyu_price”按钮，改为用户自行进入闲鱼后使用浮层
- 自检结论：
  - 目标 1-5 已全部达成
  - 当前剩余问题是 Apple 搜索结果页里“精确规格”偶尔会从 `MacBook Pro 14` 漂到更高置信的 `MacBook Pro / 14in / M4 / 16G / 512G`
  - 这不阻塞当前“浮层截图 -> 行情判断”目标，但需要继续优化以减少误判
- 下一步：继续优化 OCR 合并和 Apple 精确规格匹配规则
