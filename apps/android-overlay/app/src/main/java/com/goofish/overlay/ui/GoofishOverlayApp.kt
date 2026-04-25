package com.goofish.overlay.ui

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Assessment
import androidx.compose.material.icons.rounded.CameraAlt
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.goofish.overlay.capture.OverlayCaptureController
import com.goofish.overlay.capture.OverlayCaptureService

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GoofishOverlayApp() {
    val context = LocalContext.current
    val state by OverlayCaptureController.state.collectAsState()
    var selectedTab by rememberSaveable { mutableStateOf(OverlayTab.Capture) }
    val background = Brush.verticalGradient(
        colors = listOf(Color(0xFF0D1B2A), Color(0xFF1B263B), Color(0xFF415A77)),
    )
    val mediaProjectionManager = remember(context) {
        context.getSystemService(MediaProjectionManager::class.java)
    }
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted ->
        OverlayCaptureController.updateNotificationPermission(granted)
    }
    val overlayPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.StartActivityForResult(),
    ) {
        OverlayCaptureController.updateOverlayPermission(Settings.canDrawOverlays(context))
    }
    val screenCaptureLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        val data = result.data
        if (result.resultCode == Activity.RESULT_OK && data != null) {
            ContextCompat.startForegroundService(
                context,
                OverlayCaptureService.buildStartIntent(
                    context = context,
                    resultCode = result.resultCode,
                    projectionData = data,
                ),
            )
        } else {
            OverlayCaptureController.updateStatus("未授予截屏权限，浮层尚未启动")
        }
    }

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Text(
                        text = selectedTab.title,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = Color.Transparent,
                    titleContentColor = Color.White,
                ),
            )
        },
        bottomBar = {
            NavigationBar(
                containerColor = Color(0xFF10243A),
                contentColor = Color.White,
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 8.dp),
                    horizontalArrangement = Arrangement.SpaceEvenly,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    OverlayTab.entries.forEach { tab ->
                        val selected = selectedTab == tab
                        val contentColor = if (selected) {
                            Color.White
                        } else {
                            Color.White.copy(alpha = 0.66f)
                        }
                        Column(
                            modifier = Modifier
                                .weight(1f)
                                .clickable { selectedTab = tab }
                                .padding(vertical = 8.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            Text(
                                text = tab.label,
                                style = MaterialTheme.typography.labelMedium,
                                color = contentColor,
                                fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium,
                            )
                            Icon(
                                imageVector = tab.icon,
                                contentDescription = tab.label,
                                tint = contentColor,
                            )
                        }
                    }
                }
            }
        },
        containerColor = Color.Transparent,
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(background)
                .padding(innerPadding),
        ) {
            LazyColumn(
                contentPadding = PaddingValues(20.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                when (selectedTab) {
                    OverlayTab.Capture -> {
                        item {
                            HeroCard(
                                title = "二手估价",
                                body = "进入闲鱼后点浮层截图，自动识别商品信息，再回查行情趋势、安全收货价和快速收货判断。",
                            )
                        }
                        item {
                            ActionCard(
                                title = "权限与服务",
                                body = buildString {
                                    appendLine("浮层权限：${if (state.overlayPermissionGranted) "已授权" else "未授权"}")
                                    appendLine("通知权限：${if (state.notificationPermissionGranted) "已授权" else "未授权"}")
                                    appendLine("浮层服务：${if (state.serviceRunning) "运行中" else "未启动"}")
                                    append("最近状态：${state.statusMessage}")
                                },
                            ) {
                                PermissionButtons(
                                    onRequestOverlay = {
                                        overlayPermissionLauncher.launch(
                                            Intent(
                                                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                                Uri.parse("package:${context.packageName}"),
                                            ),
                                        )
                                    },
                                    onRequestNotification = {
                                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                                            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                                        } else {
                                            OverlayCaptureController.updateNotificationPermission(granted = true)
                                        }
                                    },
                                    onStartOverlay = {
                                        if (!Settings.canDrawOverlays(context)) {
                                            OverlayCaptureController.updateStatus("请先授予浮层权限")
                                            return@PermissionButtons
                                        }
                                        screenCaptureLauncher.launch(mediaProjectionManager.createScreenCaptureIntent())
                                    },
                                    onStopOverlay = {
                                        context.startService(OverlayCaptureService.buildStopIntent(context))
                                    },
                                )
                            }
                        }
                        item {
                            ActionCard(
                                title = "截图产物",
                                body = buildString {
                                    appendLine(state.lastCapturePath ?: "暂无截图")
                                    if (state.lastCaptureAtLabel.isNotBlank()) {
                                        append("最近截图时间：${state.lastCaptureAtLabel}")
                                    }
                                },
                            ) {
                                Text(
                                    text = "浮层跑起来后，去闲鱼页面点圆形“截”按钮，会自动走截图、OCR 和行情分析。",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = Color.White.copy(alpha = 0.82f),
                                )
                            }
                        }
                        item {
                            RoadmapCard(
                                title = "使用方式",
                                body = "1. 授权浮层和通知\n2. 授权截屏并启动浮层\n3. 打开闲鱼后点击浮层“截”按钮",
                            )
                        }
                    }

                    OverlayTab.Analysis -> {
                        item {
                            AnalysisCard(
                                statusLabel = state.lastAnalysisStatusLabel,
                                summary = state.lastAnalysisSummary,
                                matchedLabel = state.lastMatchedLabel,
                                detectedTitle = state.lastDetectedTitle,
                                priceBandLabel = state.lastPriceBandLabel,
                                trendLabel = state.lastTrendLabel,
                                riskFlags = state.lastRiskFlags,
                                analysisInFlight = state.analysisInFlight,
                            )
                        }
                        item {
                            RoadmapCard(
                                title = "最终目标",
                                body = "进入闲鱼后点浮层即可截图，自动识别商品参数并结合数据库行情输出“是否适合快速收货”。",
                            )
                        }
                    }

                    OverlayTab.Settings -> {
                        item {
                            BackendCard(
                                backendBaseUrl = state.backendBaseUrl,
                                analysisInFlight = state.analysisInFlight,
                                onSave = { url ->
                                    OverlayCaptureController.updateBackendBaseUrl(context, url)
                                    OverlayCaptureController.updateStatus("分析后端已更新")
                                },
                            )
                        }
                        item {
                            ActionCard(
                                title = "当前环境",
                                body = buildString {
                                    appendLine("默认对齐 xianyu_price 的能力流")
                                    appendLine("不主动唤起目标应用")
                                    append("当前服务状态：${if (state.serviceRunning) "浮层运行中" else "浮层未启动"}")
                                },
                            ) {
                                Text(
                                    text = "如果手机当前网络访问不到域名，可以先切到支持 IPv6 的网络，或者临时改回本地联调地址。",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = Color.White.copy(alpha = 0.82f),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

private enum class OverlayTab(
    val label: String,
    val title: String,
    val icon: ImageVector,
) {
    Capture(label = "操作", title = "行情速查", icon = Icons.Rounded.CameraAlt),
    Analysis(label = "结果", title = "分析结果", icon = Icons.Rounded.Assessment),
    Settings(label = "设置", title = "服务设置", icon = Icons.Rounded.Settings),
}

@Composable
private fun HeroCard(
    title: String,
    body: String,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White.copy(alpha = 0.10f)),
        shape = RoundedCornerShape(24.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.headlineSmall,
                color = Color.White,
                fontWeight = FontWeight.Bold,
            )
            Spacer(modifier = Modifier.height(12.dp))
            Text(
                text = body,
                style = MaterialTheme.typography.bodyLarge,
                color = Color.White.copy(alpha = 0.88f),
            )
        }
    }
}

@Composable
private fun ActionCard(
    title: String,
    body: String,
    content: @Composable () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White.copy(alpha = 0.10f)),
        shape = RoundedCornerShape(24.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = Color.White,
            )
            Text(
                text = body,
                style = MaterialTheme.typography.bodyMedium,
                color = Color.White.copy(alpha = 0.88f),
            )
            content()
        }
    }
}

@Composable
private fun BackendCard(
    backendBaseUrl: String,
    analysisInFlight: Boolean,
    onSave: (String) -> Unit,
) {
    var backendInput by remember(backendBaseUrl) {
        mutableStateOf(backendBaseUrl)
    }
    ActionCard(
        title = "分析后端",
        body = buildString {
            appendLine("当前地址：$backendBaseUrl")
            appendLine("默认指向 .4 服务器：web.privateaitool.top:3003")
            appendLine("本地联调时可改成 127.0.0.1:8787，并在电脑执行 adb reverse")
            append(if (analysisInFlight) "当前分析状态：进行中" else "当前分析状态：空闲")
        },
    ) {
        OutlinedTextField(
            value = backendInput,
            onValueChange = { backendInput = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("后端地址") },
            singleLine = true,
        )
        Button(
            onClick = { onSave(backendInput) },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("保存后端地址")
        }
    }
}

@Composable
private fun AnalysisCard(
    statusLabel: String,
    summary: String,
    matchedLabel: String,
    detectedTitle: String,
    priceBandLabel: String,
    trendLabel: String,
    riskFlags: List<String>,
    analysisInFlight: Boolean,
) {
    ActionCard(
        title = "最新分析",
        body = buildString {
            appendLine("状态：${statusLabel.ifBlank { "暂无" }}")
            if (matchedLabel.isNotBlank()) {
                appendLine("匹配型号：$matchedLabel")
            }
            if (priceBandLabel.isNotBlank()) {
                appendLine("价格带：$priceBandLabel")
            }
            if (trendLabel.isNotBlank()) {
                appendLine("趋势：$trendLabel")
            }
            append("结论：$summary")
        },
    ) {
        if (analysisInFlight) {
            CircularProgressIndicator(
                color = Color.White,
            )
        }
        if (detectedTitle.isNotBlank()) {
            Text(
                text = "OCR 标题：$detectedTitle",
                style = MaterialTheme.typography.bodySmall,
                color = Color.White.copy(alpha = 0.88f),
            )
        }
        if (riskFlags.isNotEmpty()) {
            Text(
                text = "风险提示：${riskFlags.joinToString(" / ")}",
                style = MaterialTheme.typography.bodySmall,
                color = Color(0xFFFFE082),
            )
        }
    }
}

@Composable
private fun PermissionButtons(
    onRequestOverlay: () -> Unit,
    onRequestNotification: () -> Unit,
    onStartOverlay: () -> Unit,
    onStopOverlay: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Button(
            onClick = onRequestOverlay,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("授予浮层权限")
        }
        Button(
            onClick = onRequestNotification,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("授予通知权限")
        }
        Button(
            onClick = onStartOverlay,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("授予截屏权限并启动浮层")
        }
        OutlinedButton(
            onClick = onStopOverlay,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("停止浮层服务")
        }
    }
}

@Composable
private fun RoadmapCard(title: String, body: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(20.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(18.dp),
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = Color(0xFF102A43),
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = body,
                style = MaterialTheme.typography.bodyMedium,
                color = Color(0xFF334E68),
            )
        }
    }
}
