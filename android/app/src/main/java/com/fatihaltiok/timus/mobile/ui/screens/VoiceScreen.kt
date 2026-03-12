package com.fatihaltiok.timus.mobile.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.fatihaltiok.timus.mobile.model.VoiceUiState
import com.fatihaltiok.timus.mobile.ui.components.TimusCard
import com.fatihaltiok.timus.mobile.ui.components.VoiceOrb
import com.fatihaltiok.timus.mobile.ui.theme.GlowPrimary
import com.fatihaltiok.timus.mobile.ui.theme.Night0
import com.fatihaltiok.timus.mobile.ui.theme.Night1
import com.fatihaltiok.timus.mobile.ui.theme.Panel
import com.fatihaltiok.timus.mobile.ui.theme.PanelStrong
import com.fatihaltiok.timus.mobile.ui.theme.TextMuted
import com.fatihaltiok.timus.mobile.ui.theme.TimusPrimary
import com.fatihaltiok.timus.mobile.ui.theme.statusColorFor
import java.io.File

@Composable
fun VoiceScreen(
    voiceState: VoiceUiState,
    onRefreshStatus: () -> Unit,
    onSendTranscript: () -> Unit,
    onTranscribeAudio: (fileName: String, mimeType: String, audioBytes: ByteArray) -> Unit,
    onSynthesize: () -> Unit,
    onSetVoiceState: (String) -> Unit,
) {
    val context = LocalContext.current
    var recorder by remember { mutableStateOf<MediaRecorder?>(null) }
    var recordingFile by remember { mutableStateOf<File?>(null) }
    var permissionGranted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.RECORD_AUDIO,
            ) == PackageManager.PERMISSION_GRANTED,
        )
    }
    val latestSetVoiceState by rememberUpdatedState(onSetVoiceState)
    val latestTranscribe by rememberUpdatedState(onTranscribeAudio)

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted ->
        permissionGranted = granted
        if (!granted) {
            latestSetVoiceState("error")
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            recorder?.runCatching { stop() }
            recorder?.release()
        }
    }

    fun startRecording() {
        if (!permissionGranted) {
            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            return
        }
        val file = File(context.cacheDir, "timus-mobile-recording.m4a")
        val newRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }
        newRecorder.apply {
            setAudioSource(MediaRecorder.AudioSource.MIC)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            setAudioEncodingBitRate(128_000)
            setAudioSamplingRate(44_100)
            setOutputFile(file.absolutePath)
            prepare()
            start()
        }
        recordingFile = file
        recorder = newRecorder
        onSetVoiceState("listening")
    }

    fun stopRecording() {
        val currentRecorder = recorder ?: return
        runCatching {
            currentRecorder.stop()
            currentRecorder.release()
        }
        recorder = null
        val file = recordingFile
        recordingFile = null
        if (file != null && file.exists()) {
            onSetVoiceState("transcribing")
            latestTranscribe(file.name, "audio/mp4", file.readBytes())
        } else {
            onSetVoiceState("error")
        }
    }

    fun playLastReplyAudio() {
        val audio = voiceState.lastSynthesizedAudio ?: return
        val file = File(context.cacheDir, "timus-last-reply.mp3")
        file.writeBytes(audio)
        val player = MediaPlayer().apply {
            setDataSource(file.absolutePath)
            prepare()
            setOnCompletionListener {
                onSetVoiceState("idle")
                release()
            }
            setOnErrorListener { mp, _, _ ->
                onSetVoiceState("error")
                mp.release()
                true
            }
        }
        onSetVoiceState("speaking")
        player.start()
    }

    LaunchedEffect(voiceState.playbackNonce) {
        if (voiceState.playbackNonce > 0 && voiceState.lastSynthesizedAudio != null) {
            playLastReplyAudio()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(34.dp))
                .background(
                    Brush.verticalGradient(
                        colors = listOf(PanelStrong, Panel, Night1),
                    ),
                )
                .padding(vertical = 28.dp, horizontal = 20.dp),
            contentAlignment = Alignment.Center,
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Box(
                    modifier = Modifier
                        .size(190.dp)
                        .clip(CircleShape)
                        .background(GlowPrimary.copy(alpha = 0.10f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Box(
                        modifier = Modifier
                            .size(146.dp)
                            .clip(CircleShape)
                            .background(GlowPrimary.copy(alpha = 0.08f)),
                        contentAlignment = Alignment.Center,
                    ) {
                        VoiceOrb(state = voiceState.state, size = 74.dp)
                    }
                }
                Text(
                    text = voiceState.state.uppercase(),
                    fontWeight = FontWeight.Bold,
                    color = statusColorFor(voiceState.state),
                )
                Text(
                    text = voiceState.statusMessage.ifBlank { "Voice-first Gespräch mit Timus" },
                    color = TextMuted,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(22.dp))
                .background(Panel.copy(alpha = 0.65f))
                .padding(horizontal = 16.dp, vertical = 14.dp),
        ) {
            Text(
                text = "Sprich mit Timus wie mit einem persönlichen Operator. Aufnahme, Transkript und Antwort laufen direkt in einem Voice-Flow.",
                color = TextMuted,
            )
        }

        TimusCard(
            title = "Transkript",
            subtitle = voiceState.transcript.ifBlank { "Noch kein Transkript." },
            status = if (voiceState.transcript.isBlank()) "idle" else "ok",
        )
        TimusCard(
            title = "Letzte Antwort",
            subtitle = voiceState.lastReply.ifBlank { "Noch keine Antwort." },
            status = if (voiceState.lastReply.isBlank()) "idle" else "ok",
        )
        TimusCard(
            title = "Aktive Stimme",
            subtitle = if (voiceState.currentVoice.isBlank()) {
                "Noch nicht geladen"
            } else {
                voiceState.currentVoice
            },
            status = voiceState.state,
        )

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 4.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Button(
                onClick = {
                    if (voiceState.state == "listening") {
                        stopRecording()
                    } else {
                        startRecording()
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = TimusPrimary,
                    contentColor = Night0,
                ),
            ) {
                Text(if (voiceState.state == "listening") "Aufnahme stoppen" else "Aufnahme starten")
            }
            Button(
                onClick = onSendTranscript,
                modifier = Modifier.fillMaxWidth(),
                enabled = voiceState.transcript.isNotBlank(),
                colors = ButtonDefaults.buttonColors(containerColor = PanelStrong),
            ) {
                Text("Transkript manuell senden")
            }
            Button(
                onClick = onSynthesize,
                modifier = Modifier.fillMaxWidth(),
                enabled = voiceState.lastReply.isNotBlank(),
                colors = ButtonDefaults.buttonColors(containerColor = PanelStrong),
            ) {
                Text("Antwort manuell in Audio umwandeln")
            }
            Button(
                onClick = ::playLastReplyAudio,
                modifier = Modifier.fillMaxWidth(),
                enabled = voiceState.lastSynthesizedAudio != null,
                colors = ButtonDefaults.buttonColors(containerColor = PanelStrong),
            ) {
                Text("Letzte Audioantwort abspielen")
            }
            Button(
                onClick = onRefreshStatus,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Night1),
            ) {
                Text("Voice-Status aktualisieren")
            }
        }
    }
}
