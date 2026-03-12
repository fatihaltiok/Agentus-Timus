package com.fatihaltiok.timus.mobile.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fatihaltiok.timus.mobile.data.NetworkTimusRepository
import com.fatihaltiok.timus.mobile.data.TimusConfig
import com.fatihaltiok.timus.mobile.data.TimusRepository
import com.fatihaltiok.timus.mobile.model.ChatMessage
import com.fatihaltiok.timus.mobile.model.VoiceUiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID

data class AppSessionUiState(
    val config: TimusConfig = TimusConfig(),
    val authenticated: Boolean = false,
    val sessionId: String = "android_" + UUID.randomUUID().toString().take(8),
    val messages: List<ChatMessage> = emptyList(),
    val draft: String = "",
    val loading: Boolean = false,
    val error: String? = null,
    val voice: VoiceUiState = VoiceUiState(),
)

class AppSessionViewModel(
    private val repository: TimusRepository = NetworkTimusRepository(),
) : ViewModel() {

    private val _uiState = MutableStateFlow(AppSessionUiState())
    val uiState: StateFlow<AppSessionUiState> = _uiState.asStateFlow()

    fun login(config: TimusConfig) {
        _uiState.value = _uiState.value.copy(
            config = config,
            authenticated = config.baseUrl.isNotBlank(),
            error = null,
        )
        refreshVoiceStatus()
        loadChatHistory()
    }

    fun updateDraft(value: String) {
        _uiState.value = _uiState.value.copy(draft = value)
    }

    fun loadChatHistory() {
        val state = _uiState.value
        if (!state.authenticated) return
        viewModelScope.launch {
            repository.loadChatHistory(state.config)
                .onSuccess { history ->
                    _uiState.value = _uiState.value.copy(messages = history, error = null)
                }
                .onFailure { error ->
                    _uiState.value = _uiState.value.copy(error = error.message)
                }
        }
    }

    fun sendDraft() {
        sendMessage(_uiState.value.draft.trim(), fromVoice = false)
    }

    private fun sendMessage(message: String, fromVoice: Boolean) {
        val state = _uiState.value
        if (message.isBlank() || !state.authenticated) return

        val optimisticMessage = ChatMessage(role = "user", text = message)
        _uiState.value = state.copy(
            loading = true,
            draft = if (fromVoice) message else "",
            error = null,
            messages = state.messages + optimisticMessage,
            voice = state.voice.copy(
                state = "thinking",
                transcript = message,
                statusMessage = if (fromVoice) "Verarbeite Sprachanfrage…" else state.voice.statusMessage,
            ),
        )

        viewModelScope.launch {
            repository.sendChatMessage(
                config = state.config,
                query = message,
                sessionId = state.sessionId,
            ).onSuccess { reply ->
                val nextState = _uiState.value.copy(
                    sessionId = reply.sessionId,
                    loading = false,
                    messages = _uiState.value.messages + ChatMessage(
                        role = "assistant",
                        text = reply.reply,
                        agent = reply.agent,
                    ),
                    voice = _uiState.value.voice.copy(
                        state = if (fromVoice) "speaking" else "idle",
                        lastReply = reply.reply,
                        statusMessage = "Antwort von ${reply.agent}",
                    ),
                    error = null,
                )
                _uiState.value = nextState
                if (fromVoice) {
                    synthesizeLastReply()
                }
            }.onFailure { error ->
                _uiState.value = _uiState.value.copy(
                    loading = false,
                    error = error.message,
                    voice = _uiState.value.voice.copy(state = "error"),
                )
            }
        }
    }

    fun refreshVoiceStatus() {
        val state = _uiState.value
        if (!state.authenticated) return
        viewModelScope.launch {
            repository.fetchVoiceStatus(state.config)
                .onSuccess { voiceStatus ->
                    _uiState.value = _uiState.value.copy(
                        voice = _uiState.value.voice.copy(
                            state = when {
                                voiceStatus.speaking -> "speaking"
                                voiceStatus.listening -> "listening"
                                else -> "idle"
                            },
                            currentVoice = voiceStatus.currentVoice,
                            availableVoices = voiceStatus.availableVoices,
                            statusMessage = if (voiceStatus.initialized) {
                                "Voice bereit"
                            } else {
                                "Voice noch nicht initialisiert"
                            },
                        ),
                    )
                }
                .onFailure { error ->
                    _uiState.value = _uiState.value.copy(
                        error = error.message,
                        voice = _uiState.value.voice.copy(state = "error"),
                    )
                }
        }
    }

    fun transcribeRecordedAudio(
        fileName: String,
        mimeType: String,
        audioBytes: ByteArray,
    ) {
        val state = _uiState.value
        if (!state.authenticated) return
        _uiState.value = state.copy(
            voice = state.voice.copy(
                state = "transcribing",
                statusMessage = "Transkribiere…",
            ),
            error = null,
        )
        viewModelScope.launch {
            repository.transcribeAudio(state.config, fileName, mimeType, audioBytes)
                .onSuccess { transcript ->
                    _uiState.value = _uiState.value.copy(
                        draft = transcript,
                        voice = _uiState.value.voice.copy(
                            state = "thinking",
                            transcript = transcript,
                            statusMessage = "Transkript bereit — sende an Timus…",
                        ),
                    )
                    sendMessage(transcript, fromVoice = true)
                }
                .onFailure { error ->
                    _uiState.value = _uiState.value.copy(
                        error = error.message,
                        voice = _uiState.value.voice.copy(state = "error", statusMessage = "Transkript fehlgeschlagen"),
                    )
                }
        }
    }

    fun synthesizeLastReply() {
        val state = _uiState.value
        val text = state.voice.lastReply.trim()
        if (!state.authenticated || text.isBlank()) return
        _uiState.value = state.copy(
            voice = state.voice.copy(
                state = "speaking",
                statusMessage = "Erzeuge Audio…",
            ),
            error = null,
        )
        viewModelScope.launch {
            repository.synthesizeSpeech(state.config, text, state.voice.currentVoice.ifBlank { null })
                .onSuccess { audio ->
                    _uiState.value = _uiState.value.copy(
                        voice = _uiState.value.voice.copy(
                            state = "speaking",
                            lastSynthesizedAudio = audio,
                            statusMessage = "Audio bereit",
                            playbackNonce = _uiState.value.voice.playbackNonce + 1,
                        ),
                    )
                }
                .onFailure { error ->
                    _uiState.value = _uiState.value.copy(
                        error = error.message,
                        voice = _uiState.value.voice.copy(state = "error", statusMessage = "TTS fehlgeschlagen"),
                    )
                }
        }
    }

    fun setVoiceState(state: String) {
        _uiState.value = _uiState.value.copy(
            voice = _uiState.value.voice.copy(state = state),
        )
    }
}
