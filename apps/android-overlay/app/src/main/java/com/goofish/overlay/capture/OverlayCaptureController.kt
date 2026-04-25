package com.goofish.overlay.capture

import android.content.Context
import com.goofish.overlay.analysis.OverlayAnalysisSnapshot
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private const val DEFAULT_BACKEND_BASE_URL = "http://web.privateaitool.top:3003"

data class OverlayCaptureState(
    val overlayPermissionGranted: Boolean = false,
    val notificationPermissionGranted: Boolean = false,
    val serviceRunning: Boolean = false,
    val statusMessage: String = "等待授权",
    val backendBaseUrl: String = DEFAULT_BACKEND_BASE_URL,
    val analysisInFlight: Boolean = false,
    val lastCapturePath: String? = null,
    val lastCaptureAtLabel: String = "",
    val lastDetectedTitle: String = "",
    val lastAnalysisStatusLabel: String = "",
    val lastAnalysisSummary: String = "暂无分析结果",
    val lastMatchedLabel: String = "",
    val lastPriceBandLabel: String = "",
    val lastTrendLabel: String = "",
    val lastRiskFlags: List<String> = emptyList(),
)

object OverlayCaptureController {
    private val formatter = SimpleDateFormat("MM-dd HH:mm:ss", Locale.getDefault())
    private val _state = MutableStateFlow(OverlayCaptureState())
    val state = _state.asStateFlow()
    private var initialized = false

    fun initialize(context: Context) {
        if (initialized) {
            return
        }
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val backendBaseUrl = prefs.getString(KEY_BACKEND_BASE_URL, DEFAULT_BACKEND_BASE_URL)
            ?.trim()
            ?.ifBlank { DEFAULT_BACKEND_BASE_URL }
            ?: DEFAULT_BACKEND_BASE_URL
        _state.value = _state.value.copy(backendBaseUrl = backendBaseUrl)
        initialized = true
    }

    fun updateOverlayPermission(granted: Boolean) {
        _state.value = _state.value.copy(overlayPermissionGranted = granted)
    }

    fun updateNotificationPermission(granted: Boolean) {
        _state.value = _state.value.copy(notificationPermissionGranted = granted)
    }

    fun updateServiceRunning(running: Boolean) {
        _state.value = _state.value.copy(serviceRunning = running)
    }

    fun updateStatus(message: String) {
        _state.value = _state.value.copy(statusMessage = message)
    }

    fun currentBackendBaseUrl(): String {
        return _state.value.backendBaseUrl
    }

    fun updateBackendBaseUrl(context: Context, url: String) {
        val normalized = url.trim().trimEnd('/').ifBlank { DEFAULT_BACKEND_BASE_URL }
        context.applicationContext
            .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_BACKEND_BASE_URL, normalized)
            .apply()
        _state.value = _state.value.copy(backendBaseUrl = normalized)
    }

    fun updateCapture(path: String) {
        _state.value = _state.value.copy(
            lastCapturePath = path,
            lastCaptureAtLabel = formatter.format(Date()),
            statusMessage = "截图完成",
        )
    }

    fun updateAnalysisRunning(message: String) {
        _state.value = _state.value.copy(
            analysisInFlight = true,
            statusMessage = message,
        )
    }

    fun updateAnalysisResult(snapshot: OverlayAnalysisSnapshot) {
        _state.value = _state.value.copy(
            analysisInFlight = false,
            statusMessage = snapshot.summary,
            lastDetectedTitle = snapshot.detectedTitle,
            lastAnalysisStatusLabel = snapshot.statusLabel,
            lastAnalysisSummary = snapshot.summary,
            lastMatchedLabel = snapshot.matchedLabel,
            lastPriceBandLabel = snapshot.priceBandLabel,
            lastTrendLabel = snapshot.trendLabel,
            lastRiskFlags = snapshot.riskFlags,
        )
    }

    fun updateAnalysisFailure(message: String) {
        _state.value = _state.value.copy(
            analysisInFlight = false,
            statusMessage = message,
            lastAnalysisStatusLabel = "失败",
            lastAnalysisSummary = message,
            lastRiskFlags = listOf(message),
        )
    }

    private const val PREFS_NAME = "goofish_overlay_prefs"
    private const val KEY_BACKEND_BASE_URL = "backend_base_url"
}
