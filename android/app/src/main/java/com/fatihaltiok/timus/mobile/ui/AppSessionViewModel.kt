package com.fatihaltiok.timus.mobile.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fatihaltiok.timus.mobile.data.NetworkTimusRepository
import com.fatihaltiok.timus.mobile.data.TimusConfig
import com.fatihaltiok.timus.mobile.data.TimusRepository
import com.fatihaltiok.timus.mobile.model.ChatMessage
import com.fatihaltiok.timus.mobile.model.LocationServerSnapshot
import com.fatihaltiok.timus.mobile.model.LocationUiState
import com.fatihaltiok.timus.mobile.model.VoiceUiState
import com.fatihaltiok.timus.mobile.location.TimusLocationClient
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
    val location: LocationUiState = LocationUiState(),
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
        loadLocationStatus()
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
                .onFailure {
                    // Verlauf-Refresh ist Hintergrundarbeit und soll keine globale Fehlerkarte im Chat ausloesen.
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
                        state = if (fromVoice) "synthesizing" else "idle",
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
                        voice = _uiState.value.voice.copy(state = "error"),
                    )
                }
        }
    }

    fun syncLocationPermission(granted: Boolean) {
        val locationState = _uiState.value.location
        _uiState.value = _uiState.value.copy(
            location = locationState.copy(
                permissionState = if (granted) "granted" else "denied",
                state = when {
                    granted && locationState.lastResolvedLocation != null -> "ready"
                    granted -> "idle"
                    else -> "denied"
                },
                statusMessage = when {
                    granted && locationState.lastResolvedLocation != null -> locationSummary(locationState.lastResolvedLocation)
                    granted -> "Standort kann jetzt abgerufen werden"
                    else -> "Standortberechtigung fehlt"
                },
                error = if (granted) null else locationState.error,
            ),
        )
    }

    fun prepareLocationPermissionRequest() {
        _uiState.value = _uiState.value.copy(
            location = _uiState.value.location.copy(
                state = "requesting_permission",
                permissionState = "requesting",
                statusMessage = "Standortberechtigung wird angefragt…",
                error = null,
            ),
        )
    }

    fun handleLocationPermissionDenied() {
        _uiState.value = _uiState.value.copy(
            location = _uiState.value.location.copy(
                state = "denied",
                permissionState = "denied",
                statusMessage = "Standortzugriff wurde abgelehnt",
                error = null,
            ),
        )
    }

    fun loadLocationStatus() {
        val state = _uiState.value
        if (!state.authenticated) return
        viewModelScope.launch {
            repository.fetchLocationStatus(state.config)
                .onSuccess { location ->
                    if (location == null) {
                        _uiState.value = _uiState.value.copy(
                            location = _uiState.value.location.copy(
                                state = if (_uiState.value.location.permissionState == "granted") "idle" else _uiState.value.location.state,
                                statusMessage = if (_uiState.value.location.permissionState == "granted") {
                                    "Noch kein Standort synchronisiert"
                                } else {
                                    _uiState.value.location.statusMessage
                                },
                                error = null,
                            ),
                        )
                    } else {
                        _uiState.value = _uiState.value.copy(
                            location = _uiState.value.location.copy(
                                state = "ready",
                                lastResolvedLocation = location,
                                statusMessage = locationSummary(location),
                                error = null,
                            ),
                        )
                    }
                }
                .onFailure { error ->
                    _uiState.value = _uiState.value.copy(
                        location = _uiState.value.location.copy(
                            state = "error",
                            statusMessage = "Standortstatus konnte nicht geladen werden",
                            error = error.message,
                        ),
                    )
                }
        }
    }

    fun refreshLocation(locationClient: TimusLocationClient) {
        val state = _uiState.value
        if (!state.authenticated) return
        _uiState.value = state.copy(
            location = state.location.copy(
                state = "fetching",
                statusMessage = "Standort wird vom Gerät abgerufen…",
                error = null,
            ),
            error = null,
        )
        viewModelScope.launch {
            locationClient.captureCurrentLocation()
                .onSuccess { snapshot ->
                    _uiState.value = _uiState.value.copy(
                        location = _uiState.value.location.copy(
                            state = "syncing",
                            permissionState = "granted",
                            lastDeviceLocation = snapshot,
                            statusMessage = "Standort erkannt — normalisiere…",
                            error = null,
                        ),
                    )
                    repository.resolveLocation(state.config, snapshot)
                        .onSuccess { resolved ->
                            _uiState.value = _uiState.value.copy(
                                location = _uiState.value.location.copy(
                                    state = "ready",
                                    permissionState = "granted",
                                    lastResolvedLocation = resolved,
                                    statusMessage = locationSummary(resolved),
                                    error = null,
                                ),
                            )
                        }
                        .onFailure { error ->
                            _uiState.value = _uiState.value.copy(
                                location = _uiState.value.location.copy(
                                    state = "warning",
                                    permissionState = "granted",
                                    statusMessage = "Standort lokal erfasst, Server-Normalisierung fehlgeschlagen",
                                    error = error.message,
                                ),
                            )
                        }
                }
                .onFailure { error ->
                    _uiState.value = _uiState.value.copy(
                        location = _uiState.value.location.copy(
                            state = "error",
                            statusMessage = "Standort konnte nicht ermittelt werden",
                            error = error.message,
                        ),
                    )
                }
        }
    }

    fun transcribeRecordedAudio(
        fileName: String,
        mimeType: String,
        audioBytes: ByteArray,
        autoSend: Boolean = true,
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
                    if (autoSend) {
                        _uiState.value = _uiState.value.copy(
                            draft = transcript,
                            voice = _uiState.value.voice.copy(
                                state = "thinking",
                                transcript = transcript,
                                statusMessage = "Transkript bereit — sende an Timus…",
                            ),
                        )
                        sendMessage(transcript, fromVoice = true)
                    } else {
                        _uiState.value = _uiState.value.copy(
                            draft = transcript,
                            voice = _uiState.value.voice.copy(
                                state = "idle",
                                transcript = transcript,
                                statusMessage = "Transkript bereit — noch nicht an Timus gesendet",
                            ),
                        )
                    }
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
                state = "synthesizing",
                statusMessage = "Erzeuge Audio…",
            ),
            error = null,
        )
        viewModelScope.launch {
            repository.synthesizeSpeech(state.config, text, state.voice.currentVoice.ifBlank { null })
                .onSuccess { audio ->
                    _uiState.value = _uiState.value.copy(
                        voice = _uiState.value.voice.copy(
                            state = "synthesizing",
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

    private fun locationSummary(location: LocationServerSnapshot): String {
        val headline = location.displayName.ifBlank {
            listOf(location.locality, location.adminArea, location.countryName)
                .filter { it.isNotBlank() }
                .joinToString(", ")
        }.ifBlank {
            "${location.latitude}, ${location.longitude}"
        }
        val accuracy = location.accuracyMeters?.let { " ±${it.toInt()} m" } ?: ""
        return "$headline$accuracy"
    }
}
