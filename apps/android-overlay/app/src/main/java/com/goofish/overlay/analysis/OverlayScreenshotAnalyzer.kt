package com.goofish.overlay.analysis

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import android.util.Base64
import com.google.android.gms.tasks.Task
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.text.DecimalFormat
import java.time.Instant
import java.util.Locale
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

data class OverlayRecognizedLine(
    val text: String,
    val left: Int?,
    val top: Int?,
    val right: Int?,
    val bottom: Int?,
)

data class OverlayAnalysisSnapshot(
    val status: String,
    val statusLabel: String,
    val summary: String,
    val notificationText: String,
    val matchedLabel: String,
    val detectedTitle: String,
    val priceBandLabel: String,
    val trendLabel: String,
    val riskFlags: List<String>,
)

object OverlayScreenshotAnalyzer {
    suspend fun analyzeCapture(
        context: Context,
        screenshotFile: File,
        backendBaseUrl: String,
    ): OverlayAnalysisSnapshot = withContext(Dispatchers.IO) {
        val recognizedLines = recognizeText(context, screenshotFile)
        val screenSize = decodeScreenSize(screenshotFile)
        val payload = JSONObject().apply {
            put("source_package", null)
            put("captured_at", Instant.now().toString())
            put("screen_width", screenSize.first)
            put("screen_height", screenSize.second)
            put("screenshot_base64", encodeScreenshotDataUrl(screenshotFile))
            put(
                "ocr_lines",
                JSONArray().apply {
                    recognizedLines.forEach { line ->
                        put(
                            JSONObject().apply {
                                put("text", line.text)
                                put("left", line.left)
                                put("top", line.top)
                                put("right", line.right)
                                put("bottom", line.bottom)
                            },
                        )
                    }
                },
            )
        }

        val response = postAnalysisRequest(
            baseUrl = backendBaseUrl,
            payload = payload,
        )
        parseAnalysisResponse(response)
    }

    private suspend fun recognizeText(
        context: Context,
        screenshotFile: File,
    ): List<OverlayRecognizedLine> {
        val chineseLines = recognizeTextWithRecognizer(
            context = context,
            screenshotFile = screenshotFile,
            recognizer = TextRecognition.getClient(
                ChineseTextRecognizerOptions.Builder().build(),
            ),
        )
        val latinLines = recognizeTextWithRecognizer(
            context = context,
            screenshotFile = screenshotFile,
            recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS),
        )
        return mergeRecognizedLines(chineseLines, latinLines)
    }

    private suspend fun recognizeTextWithRecognizer(
        context: Context,
        screenshotFile: File,
        recognizer: TextRecognizer,
    ): List<OverlayRecognizedLine> {
        try {
            val image = InputImage.fromFilePath(context, Uri.fromFile(screenshotFile))
            val result = recognizer.process(image).await()
            return result.textBlocks
                .flatMap { block -> block.lines }
                .mapNotNull { line ->
                    val text = line.text.trim()
                    if (text.isEmpty()) {
                        return@mapNotNull null
                    }
                    val box = line.boundingBox
                    OverlayRecognizedLine(
                        text = text,
                        left = box?.left,
                        top = box?.top,
                        right = box?.right,
                        bottom = box?.bottom,
                    )
                }
        } finally {
            recognizer.close()
        }
    }

    private fun decodeScreenSize(file: File): Pair<Int?, Int?> {
        val options = BitmapFactory.Options().apply {
            inJustDecodeBounds = true
        }
        BitmapFactory.decodeFile(file.absolutePath, options)
        val width = options.outWidth.takeIf { it > 0 }
        val height = options.outHeight.takeIf { it > 0 }
        return width to height
    }

    private fun mergeRecognizedLines(vararg groups: List<OverlayRecognizedLine>): List<OverlayRecognizedLine> {
        val merged = LinkedHashMap<String, OverlayRecognizedLine>()
        groups.asList().flatten().forEach { line ->
            val key = buildString {
                append(line.text.lowercase(Locale.getDefault()).trim())
                append('|')
                append(line.left ?: -1)
                append('|')
                append(line.top ?: -1)
                append('|')
                append(line.right ?: -1)
                append('|')
                append(line.bottom ?: -1)
            }
            merged.putIfAbsent(key, line)
        }
        return merged.values.sortedWith(
            compareBy<OverlayRecognizedLine>({ it.top ?: Int.MAX_VALUE }, { it.left ?: Int.MAX_VALUE }),
        )
    }

    private fun postAnalysisRequest(
        baseUrl: String,
        payload: JSONObject,
    ): JSONObject {
        val normalizedBaseUrl = baseUrl.trim().trimEnd('/')
        val connection = (URL("$normalizedBaseUrl/api/mobile-overlay/analyze").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 10_000
            readTimeout = 300_000
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Accept", "application/json")
        }
        return try {
            connection.outputStream.use { output ->
                OutputStreamWriter(output, Charsets.UTF_8).use { writer ->
                    writer.write(payload.toString())
                }
            }
            val body = if (connection.responseCode in 200..299) {
                connection.inputStream.bufferedReader().use { it.readText() }
            } else {
                val errorBody = connection.errorStream?.bufferedReader()?.use { it.readText() }.orEmpty()
                throw IllegalStateException(
                    "分析接口返回 ${connection.responseCode}: ${errorBody.ifBlank { connection.responseMessage ?: "未知错误" }}",
                )
            }
            JSONObject(body)
        } finally {
            connection.disconnect()
        }
    }

    private fun parseAnalysisResponse(response: JSONObject): OverlayAnalysisSnapshot {
        val ocrSummary = response.optJSONObject("ocr_summary")
        val match = response.optJSONObject("match")
        val pricing = match?.optJSONObject("pricing")
        val trend = match?.optJSONObject("trend")
        val decision = response.optJSONObject("decision")

        val status = decision?.optString("status").orEmpty().ifBlank { "needs_review" }
        val summary = decision?.optString("summary").orEmpty().ifBlank { "分析已完成" }
        val matchedLabel = listOfNotNull(
            pricing?.optString("spec_label").orEmpty().takeIf { it.isNotBlank() },
            pricing?.optString("product_label").orEmpty().takeIf { it.isNotBlank() },
            pricing?.optString("label").orEmpty().takeIf { it.isNotBlank() },
        ).firstOrNull().orEmpty()
        val priceBandLabel = buildPriceBandLabel(pricing)
        val trendLabel = buildTrendLabel(trend)
        val riskFlags = decision?.optJSONArray("risk_flags").toStringList()
        val statusLabel = statusLabel(status)
        val detectedTitle = ocrSummary?.optString("title_candidate").orEmpty()
        val notificationText = when {
            matchedLabel.isBlank() -> summary
            else -> "$statusLabel $matchedLabel"
        }
        return OverlayAnalysisSnapshot(
            status = status,
            statusLabel = statusLabel,
            summary = summary,
            notificationText = notificationText,
            matchedLabel = matchedLabel,
            detectedTitle = detectedTitle,
            priceBandLabel = priceBandLabel,
            trendLabel = trendLabel,
            riskFlags = riskFlags,
        )
    }

    private fun encodeScreenshotDataUrl(file: File): String {
        val mimeType = when (file.extension.lowercase(Locale.getDefault())) {
            "jpg", "jpeg" -> "image/jpeg"
            "webp" -> "image/webp"
            else -> "image/png"
        }
        val encoded = Base64.encodeToString(file.readBytes(), Base64.NO_WRAP)
        return "data:$mimeType;base64,$encoded"
    }

    private fun buildPriceBandLabel(pricing: JSONObject?): String {
        if (pricing == null) {
            return ""
        }
        val listingPrice = pricing.optDoubleOrNull("listing_price")
        val safeBuyPrice = pricing.optDoubleOrNull("safe_buy_price")
        val targetBuyCeiling = pricing.optDoubleOrNull("target_buy_ceiling")
        val fairPrice = pricing.optDoubleOrNull("fair_price")
        val parts = buildList {
            if (listingPrice != null) {
                add("当前 ${formatCurrency(listingPrice)}")
            }
            if (safeBuyPrice != null) {
                add("安全收 ${formatCurrency(safeBuyPrice)}")
            }
            if (targetBuyCeiling != null) {
                add("目标上限 ${formatCurrency(targetBuyCeiling)}")
            }
            if (fairPrice != null) {
                add("市场中位 ${formatCurrency(fairPrice)}")
            }
        }
        return parts.joinToString(" | ")
    }

    private fun buildTrendLabel(trend: JSONObject?): String {
        if (trend == null) {
            return ""
        }
        val parts = buildList {
            trend.optString("change_label").takeIf { it.isNotBlank() }?.let(::add)
            trend.optString("latest_range_label").takeIf { it.isNotBlank() }?.let(::add)
        }
        return parts.joinToString(" | ")
    }

    private fun statusLabel(status: String): String {
        return when (status) {
            "strong_yes" -> "优先收"
            "yes" -> "可收"
            "watch" -> "观察"
            "no" -> "放弃"
            else -> "待复核"
        }
    }

    private fun formatCurrency(value: Double): String {
        val rounded = kotlin.math.round(value)
        return if (kotlin.math.abs(value - rounded) < 0.01) {
            MONEY_INTEGER_FORMAT.format(value)
        } else {
            MONEY_DECIMAL_FORMAT.format(value)
        }
    }

    private suspend fun <T> Task<T>.await(): T = suspendCancellableCoroutine { continuation ->
        addOnSuccessListener { value ->
            if (continuation.isActive) {
                continuation.resume(value)
            }
        }
        addOnFailureListener { error ->
            if (continuation.isActive) {
                continuation.resumeWithException(error)
            }
        }
        addOnCanceledListener {
            if (continuation.isActive) {
                continuation.cancel()
            }
        }
    }

    private fun JSONArray?.toStringList(): List<String> {
        if (this == null) {
            return emptyList()
        }
        return buildList {
            for (index in 0 until length()) {
                val value = optString(index).trim()
                if (value.isNotEmpty()) {
                    add(value)
                }
            }
        }
    }

    private fun JSONObject.optDoubleOrNull(key: String): Double? {
        if (!has(key) || isNull(key)) {
            return null
        }
        return optDouble(key).takeUnless { it.isNaN() }
    }

    private val MONEY_INTEGER_FORMAT = DecimalFormat("¥#,##0").apply {
        decimalFormatSymbols = decimalFormatSymbols.apply {
            currencySymbol = if (Locale.getDefault().language == Locale.CHINESE.language) "¥" else "$"
        }
    }
    private val MONEY_DECIMAL_FORMAT = DecimalFormat("¥#,##0.00").apply {
        decimalFormatSymbols = decimalFormatSymbols.apply {
            currencySymbol = if (Locale.getDefault().language == Locale.CHINESE.language) "¥" else "$"
        }
    }
}
