package com.fatihaltiok.timus.mobile.model

data class ChatMessage(
    val role: String,
    val text: String,
    val timestamp: String = "",
    val agent: String? = null,
)

data class ChatReply(
    val agent: String,
    val reply: String,
    val sessionId: String,
)

data class VoiceStatus(
    val initialized: Boolean,
    val listening: Boolean,
    val speaking: Boolean,
    val currentVoice: String,
    val availableVoices: List<String>,
)

data class VoiceUiState(
    val state: String = "idle",
    val currentVoice: String = "",
    val transcript: String = "",
    val lastReply: String = "",
    val statusMessage: String = "",
    val availableVoices: List<String> = emptyList(),
    val lastSynthesizedAudio: ByteArray? = null,
    val playbackNonce: Int = 0,
)
