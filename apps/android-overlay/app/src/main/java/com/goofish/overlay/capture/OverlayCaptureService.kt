package com.goofish.overlay.capture

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.TextView
import androidx.core.app.NotificationCompat
import com.goofish.overlay.MainActivity
import com.goofish.overlay.R
import com.goofish.overlay.analysis.OverlayScreenshotAnalyzer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.math.abs

class OverlayCaptureService : Service() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private lateinit var windowManager: WindowManager
    private lateinit var projectionManager: MediaProjectionManager

    private var overlayView: View? = null
    private var overlayLayoutParams: WindowManager.LayoutParams? = null
    private var mediaProjection: MediaProjection? = null
    private var captureInFlight = false

    override fun onCreate() {
        super.onCreate()
        OverlayCaptureController.initialize(applicationContext)
        windowManager = getSystemService(WindowManager::class.java)
        projectionManager = getSystemService(MediaProjectionManager::class.java)
        ensureNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                startForeground(NOTIFICATION_ID, buildNotification("浮层服务运行中"))
                val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0)
                val projectionData = intent.intentCompatExtra(EXTRA_RESULT_DATA)
                if (projectionData == null || resultCode == 0) {
                    OverlayCaptureController.updateStatus("缺少截屏授权结果")
                    stopSelf()
                    return START_NOT_STICKY
                }
                mediaProjection?.stop()
                mediaProjection = projectionManager.getMediaProjection(resultCode, projectionData)
                showOverlay()
                OverlayCaptureController.updateServiceRunning(true)
                OverlayCaptureController.updateStatus("浮层已启动，去闲鱼页面点“截”按钮即可截图")
            }

            ACTION_STOP -> stopSelf()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        overlayView?.let { windowManager.removeView(it) }
        overlayView = null
        overlayLayoutParams = null
        mediaProjection?.stop()
        mediaProjection = null
        OverlayCaptureController.updateServiceRunning(false)
        OverlayCaptureController.updateStatus("浮层服务已停止")
        serviceScope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun showOverlay() {
        if (overlayView != null) {
            return
        }

        val bubble = TextView(this).apply {
            text = "\u622a"
            textSize = 20f
            gravity = Gravity.CENTER
            setTextColor(0xFFFFFFFF.toInt())
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(0xFF4F46E5.toInt())
                setStroke(3, 0x66FFFFFF)
            }
        }
        val container = FrameLayout(this).apply {
            addView(bubble, FrameLayout.LayoutParams(132, 132, Gravity.CENTER))
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            },
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.END
            x = 36
            y = 320
        }

        container.setOnTouchListener(DraggableTouchListener(params))
        bubble.setOnClickListener {
            captureScreen()
        }

        windowManager.addView(container, params)
        overlayView = container
        overlayLayoutParams = params
    }

    private fun captureScreen() {
        val projection = mediaProjection
        if (projection == null) {
            OverlayCaptureController.updateStatus("截屏权限未准备好")
            return
        }
        if (captureInFlight) {
            OverlayCaptureController.updateStatus("正在截图，请稍候")
            return
        }

        captureInFlight = true
        OverlayCaptureController.updateStatus("正在截图")
        serviceScope.launch {
            runCatching {
                val file = performSingleCapture(projection)
                OverlayCaptureController.updateCapture(file.absolutePath)
                updateNotification("截图完成，开始识别")
                OverlayCaptureController.updateAnalysisRunning("正在识别截图文字")
                val analysis = OverlayScreenshotAnalyzer.analyzeCapture(
                    context = applicationContext,
                    screenshotFile = file,
                    backendBaseUrl = OverlayCaptureController.currentBackendBaseUrl(),
                )
                OverlayCaptureController.updateAnalysisResult(analysis)
                updateNotification(analysis.notificationText)
            }.onFailure { error ->
                OverlayCaptureController.updateAnalysisFailure(
                    "截图/分析失败：${error.message ?: "未知错误"}",
                )
                updateNotification("截图/分析失败")
            }
            captureInFlight = false
        }
    }

    private fun performSingleCapture(projection: MediaProjection): File {
        val metrics = resources.displayMetrics
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val density = metrics.densityDpi

        val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        val handlerThread = HandlerThread("overlay-capture").apply { start() }
        val handler = Handler(handlerThread.looper)
        val latch = CountDownLatch(1)
        var capturedImage: Image? = null

        reader.setOnImageAvailableListener({ imageReader ->
            val image = imageReader.acquireLatestImage()
            if (image != null && capturedImage == null) {
                capturedImage = image
                latch.countDown()
            } else {
                image?.close()
            }
        }, handler)

        val virtualDisplay = projection.createVirtualDisplay(
            "overlay-capture",
            width,
            height,
            density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader.surface,
            null,
            handler,
        ) ?: throw IllegalStateException("无法创建虚拟屏幕")

        try {
            if (!latch.await(3, TimeUnit.SECONDS)) {
                throw IllegalStateException("截图超时")
            }
            val image = capturedImage ?: throw IllegalStateException("未拿到截图内容")
            return image.writeToFile(width, height, captureDirectory())
        } finally {
            capturedImage?.close()
            reader.close()
            virtualDisplay.release()
            handlerThread.quitSafely()
        }
    }

    private fun captureDirectory(): File {
        return File(filesDir, "captures").apply { mkdirs() }
    }

    private fun buildNotification(content: String): Notification {
        val launchIntent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            launchIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.overlay_notification_title))
            .setContentText(content)
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(content: String) {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, buildNotification(content))
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Overlay Capture",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "闲鱼浮层截图服务"
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private inner class DraggableTouchListener(
        private val params: WindowManager.LayoutParams,
    ) : View.OnTouchListener {
        private var startX = 0
        private var startY = 0
        private var touchX = 0f
        private var touchY = 0f
        private var moved = false

        override fun onTouch(view: View, event: MotionEvent): Boolean {
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = params.x
                    startY = params.y
                    touchX = event.rawX
                    touchY = event.rawY
                    moved = false
                }

                MotionEvent.ACTION_MOVE -> {
                    val dx = (event.rawX - touchX).toInt()
                    val dy = (event.rawY - touchY).toInt()
                    if (abs(dx) > 6 || abs(dy) > 6) {
                        moved = true
                    }
                    params.x = startX - dx
                    params.y = startY + dy
                    windowManager.updateViewLayout(view, params)
                    return true
                }

                MotionEvent.ACTION_UP -> {
                    if (moved) {
                        return true
                    }
                }
            }
            return false
        }
    }

    companion object {
        private const val CHANNEL_ID = "overlay_capture"
        private const val NOTIFICATION_ID = 1001
        private const val ACTION_START = "com.goofish.overlay.action.START"
        private const val ACTION_STOP = "com.goofish.overlay.action.STOP"
        private const val EXTRA_RESULT_CODE = "result_code"
        private const val EXTRA_RESULT_DATA = "result_data"

        fun buildStartIntent(
            context: Context,
            resultCode: Int,
            projectionData: Intent,
        ): Intent {
            return Intent(context, OverlayCaptureService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_RESULT_CODE, resultCode)
                putExtra(EXTRA_RESULT_DATA, projectionData)
            }
        }

        fun buildStopIntent(context: Context): Intent {
            return Intent(context, OverlayCaptureService::class.java).apply {
                action = ACTION_STOP
            }
        }
    }
}

private fun Intent.intentCompatExtra(key: String): Intent? {
    return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        getParcelableExtra(key, Intent::class.java)
    } else {
        @Suppress("DEPRECATION")
        getParcelableExtra(key)
    }
}

private fun Image.writeToFile(width: Int, height: Int, targetDir: File): File {
    val plane = planes.first()
    val buffer = plane.buffer
    val pixelStride = plane.pixelStride
    val rowStride = plane.rowStride
    val rowPadding = rowStride - pixelStride * width
    val bitmap = Bitmap.createBitmap(
        width + rowPadding / pixelStride,
        height,
        Bitmap.Config.ARGB_8888,
    )
    bitmap.copyPixelsFromBuffer(buffer)
    val croppedBitmap = Bitmap.createBitmap(bitmap, 0, 0, width, height)
    val file = File(targetDir, "capture-${System.currentTimeMillis()}.png")
    FileOutputStream(file).use { output ->
        croppedBitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
    }
    bitmap.recycle()
    croppedBitmap.recycle()
    return file
}
