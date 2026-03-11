package com.fatihaltiok.timus.mobile.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.fatihaltiok.timus.mobile.data.TimusMockData
import com.fatihaltiok.timus.mobile.model.AppDestination
import com.fatihaltiok.timus.mobile.ui.components.TimusScaffold
import com.fatihaltiok.timus.mobile.ui.screens.AdminScreen
import com.fatihaltiok.timus.mobile.ui.screens.ChatScreen
import com.fatihaltiok.timus.mobile.ui.screens.FilesScreen
import com.fatihaltiok.timus.mobile.ui.screens.HomeScreen
import com.fatihaltiok.timus.mobile.ui.screens.LoginScreen
import com.fatihaltiok.timus.mobile.ui.screens.VoiceScreen

@Composable
fun TimusMobileApp() {
    val sessionViewModel: AppSessionViewModel = viewModel()
    val uiState by sessionViewModel.uiState.collectAsStateWithLifecycle()

    if (!uiState.authenticated) {
        LoginScreen(
            initialConfig = uiState.config,
            onLogin = {
                sessionViewModel.login(it)
            },
        )
        return
    }

    val navController = rememberNavController()
    val summary = remember(uiState.voice.state, uiState.error, uiState.voice.availableVoices) {
        TimusMockData.homeSummary.copy(
            activeAlerts = if (uiState.error.isNullOrBlank()) 0 else 1,
            voiceReady = uiState.voice.availableVoices.isNotEmpty() || uiState.voice.currentVoice.isNotBlank(),
        )
    }

    TimusScaffold(
        navController = navController,
        voiceState = uiState.voice.state,
    ) {
        NavHost(
            navController = navController,
            startDestination = AppDestination.Home.route,
        ) {
            composable(AppDestination.Home.route) {
                HomeScreen(
                    summary = summary,
                    voiceState = uiState.voice.state,
                )
            }
            composable(AppDestination.Chat.route) {
                ChatScreen(
                    messages = uiState.messages,
                    draft = uiState.draft,
                    loading = uiState.loading,
                    error = uiState.error,
                    onDraftChange = sessionViewModel::updateDraft,
                    onSend = sessionViewModel::sendDraft,
                )
            }
            composable(AppDestination.Voice.route) {
                VoiceScreen(
                    voiceState = uiState.voice,
                    onRefreshStatus = sessionViewModel::refreshVoiceStatus,
                    onSendTranscript = sessionViewModel::sendDraft,
                    onTranscribeAudio = sessionViewModel::transcribeRecordedAudio,
                    onSynthesize = sessionViewModel::synthesizeLastReply,
                    onSetVoiceState = sessionViewModel::setVoiceState,
                )
            }
            composable(AppDestination.Files.route) {
                FilesScreen()
            }
            composable(AppDestination.Admin.route) {
                AdminScreen()
            }
        }
    }
}
