package com.fatihaltiok.timus.mobile.ui.theme

import androidx.compose.ui.graphics.Color

val Night0 = Color(0xFF030B14)
val Night1 = Color(0xFF071522)
val Night2 = Color(0xFF0B1D2E)
val Night3 = Color(0xFF10263A)

val Panel = Color(0xCC0D1F31)
val PanelStrong = Color(0xE6112C42)
val PanelMuted = Color(0xB30B1723)
val PanelBorder = Color(0xFF163A56)
val PanelBorderBright = Color(0xFF1F5E88)

val TextStrong = Color(0xFFF4FBFF)
val TextMuted = Color(0xFFA6C2D8)
val TextSoft = Color(0xFF6F93AD)

val TimusPrimary = Color(0xFF2AF5C9)
val TimusPrimarySoft = Color(0xFF8BFFE6)
val TimusAccent = Color(0xFF1FD8FF)
val TimusIdle = Color(0xFF35D6E8)
val TimusOk = Color(0xFF2CF28A)
val TimusWarn = Color(0xFFFFC85C)
val TimusError = Color(0xFFFF5D67)
val TimusThinking = Color(0xFF41E5B8)

val GlowPrimary = Color(0x882AF5C9)
val GlowAccent = Color(0x5527DFFF)
val GlowWarn = Color(0x66FFC85C)
val GlowError = Color(0x66FF5D67)

fun statusColorFor(state: String): Color =
    when (state.lowercase()) {
        "ok", "healthy", "completed", "success", "speaking" -> TimusOk
        "warning", "warn", "degraded", "transcribing" -> TimusWarn
        "error", "failed", "blocked" -> TimusError
        "thinking", "synthesizing" -> TimusThinking
        "listening" -> TimusPrimary
        else -> TimusIdle
    }
