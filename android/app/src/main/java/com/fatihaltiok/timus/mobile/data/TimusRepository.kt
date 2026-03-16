package com.fatihaltiok.timus.mobile.data

import com.fatihaltiok.timus.mobile.model.ChatMessage
import com.fatihaltiok.timus.mobile.model.ChatReply
import com.fatihaltiok.timus.mobile.model.DeviceLocationSnapshot
import com.fatihaltiok.timus.mobile.model.LocationControlState
import com.fatihaltiok.timus.mobile.model.LocationServerSnapshot
import com.fatihaltiok.timus.mobile.model.VoiceStatus

interface TimusRepository {
    suspend fun sendChatMessage(
        config: TimusConfig,
        query: String,
        sessionId: String,
    ): Result<ChatReply>

    suspend fun loadChatHistory(config: TimusConfig): Result<List<ChatMessage>>

    suspend fun fetchVoiceStatus(config: TimusConfig): Result<VoiceStatus>

    suspend fun transcribeAudio(
        config: TimusConfig,
        fileName: String,
        mimeType: String,
        audioBytes: ByteArray,
    ): Result<String>

    suspend fun synthesizeSpeech(
        config: TimusConfig,
        text: String,
        voice: String? = null,
    ): Result<ByteArray>

    suspend fun fetchLocationStatus(config: TimusConfig): Result<LocationServerSnapshot?>

    suspend fun fetchLocationControlStatus(config: TimusConfig): Result<LocationControlState>

    suspend fun updateLocationControl(
        config: TimusConfig,
        controls: LocationControlState,
    ): Result<LocationControlState>

    suspend fun resolveLocation(
        config: TimusConfig,
        location: DeviceLocationSnapshot,
    ): Result<LocationServerSnapshot>
}
