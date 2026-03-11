package com.fatihaltiok.timus.mobile.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val TimusDarkColors = darkColorScheme(
    primary = Glow,
    onPrimary = Night0,
    secondary = Accent,
    onSecondary = Night0,
    tertiary = GlowSoft,
    background = Night0,
    onBackground = TextStrong,
    surface = Night1,
    onSurface = TextStrong,
    surfaceVariant = Panel,
    onSurfaceVariant = TextMuted,
    error = Danger,
)

@Composable
fun TimusTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = TimusDarkColors,
        typography = TimusTypography,
        content = content,
    )
}
