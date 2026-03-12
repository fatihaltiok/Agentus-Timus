package com.fatihaltiok.timus.mobile.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val TimusDarkColors = darkColorScheme(
    primary = TimusPrimary,
    onPrimary = Night0,
    secondary = TimusAccent,
    onSecondary = Night0,
    tertiary = TimusPrimarySoft,
    background = Night0,
    onBackground = TextStrong,
    surface = Night1,
    onSurface = TextStrong,
    surfaceVariant = PanelStrong,
    onSurfaceVariant = TextMuted,
    error = TimusError,
    outline = PanelBorder,
    outlineVariant = PanelBorderBright,
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
