package com.goofish.overlay

import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.goofish.overlay.capture.OverlayCaptureController
import com.goofish.overlay.ui.GoofishOverlayApp
import com.goofish.overlay.ui.theme.GoofishOverlayTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        OverlayCaptureController.initialize(applicationContext)
        enableEdgeToEdge()
        setContent {
            GoofishOverlayTheme {
                GoofishOverlayApp()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        OverlayCaptureController.updateOverlayPermission(Settings.canDrawOverlays(this))
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            OverlayCaptureController.updateNotificationPermission(granted = true)
        }
    }
}
