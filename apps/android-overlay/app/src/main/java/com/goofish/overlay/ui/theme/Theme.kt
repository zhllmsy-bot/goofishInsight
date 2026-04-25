package com.goofish.overlay.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val OverlayColorScheme = darkColorScheme(
    primary = MistWhite,
    secondary = SoftBlue,
    background = OceanBlue,
    surface = DeepSlate,
)

@Composable
fun GoofishOverlayTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = OverlayColorScheme,
        typography = Typography,
        content = content,
    )
}
