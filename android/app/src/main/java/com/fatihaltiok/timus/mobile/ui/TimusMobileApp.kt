package com.fatihaltiok.timus.mobile.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.fatihaltiok.timus.mobile.data.TimusConfigStore
import com.fatihaltiok.timus.mobile.data.TimusMockData
import com.fatihaltiok.timus.mobile.location.AndroidLocationClient
import com.fatihaltiok.timus.mobile.model.AppDestination
import com.fatihaltiok.timus.mobile.ui.components.TimusScaffold
import com.fatihaltiok.timus.mobile.ui.screens.AdminScreen
import com.fatihaltiok.timus.mobile.ui.screens.ChatScreen
import com.fatihaltiok.timus.mobile.ui.screens.FilesScreen
import com.fatihaltiok.timus.mobile.ui.screens.HomeScreen
import com.fatihaltiok.timus.mobile.ui.screens.LoginScreen
import com.fatihaltiok.timus.mobile.ui.screens.VoiceScreen
import kotlinx.coroutines.delay

@Composable
fun TimusMobileApp() {
    val sessionViewModel: AppSessionViewModel = viewModel()
    val uiState by sessionViewModel.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val configStore = remember(context) { TimusConfigStore(context) }
    val locationClient = remember(context) { AndroidLocationClient(context) }
    var autoLoginChecked by remember { mutableStateOf(false) }
    val hasLocationPermission = remember(context, uiState.authenticated, uiState.location.permissionState) {
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
    }
    val locationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions(),
    ) { permissions ->
        val granted = permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
            permissions[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        if (granted) {
            sessionViewModel.syncLocationPermission(true)
            sessionViewModel.refreshLocation(locationClient)
        } else {
            sessionViewModel.handleLocationPermissionDenied()
        }
    }

    LaunchedEffect(Unit) {
        if (!autoLoginChecked) {
            configStore.load()?.let { savedConfig ->
                sessionViewModel.login(savedConfig)
            }
            autoLoginChecked = true
        }
    }

    if (!autoLoginChecked) {
        Column(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            CircularProgressIndicator()
            Text("Stelle Timus-Session wieder her")
        }
        return
    }

    if (!uiState.authenticated) {
        LoginScreen(
            initialConfig = uiState.config,
            onLogin = {
                configStore.save(it)
                sessionViewModel.login(it)
            },
        )
        return
    }

    LaunchedEffect(hasLocationPermission) {
        sessionViewModel.syncLocationPermission(hasLocationPermission)
    }

    LaunchedEffect(uiState.authenticated, hasLocationPermission) {
        if (!uiState.authenticated || !hasLocationPermission) {
            return@LaunchedEffect
        }
        while (true) {
            sessionViewModel.autoSyncLocationIfDue(
                locationClient = locationClient,
                permissionGranted = hasLocationPermission,
            )
            delay(60_000L)
        }
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
                    locationState = uiState.location,
                    onRefreshLocation = {
                        if (hasLocationPermission) {
                            sessionViewModel.refreshLocation(locationClient)
                        } else {
                            sessionViewModel.prepareLocationPermissionRequest()
                            locationPermissionLauncher.launch(
                                arrayOf(
                                    Manifest.permission.ACCESS_FINE_LOCATION,
                                    Manifest.permission.ACCESS_COARSE_LOCATION,
                                ),
                            )
                        }
                    },
                    onRefreshLocationControls = sessionViewModel::loadLocationControlStatus,
                    onToggleLocationSharing = sessionViewModel::setLocationSharingEnabled,
                    onToggleLocationContext = sessionViewModel::setLocationContextEnabled,
                    onToggleLocationBackgroundSync = sessionViewModel::setLocationBackgroundSyncAllowed,
                    onPreferCurrentDevice = sessionViewModel::preferCurrentLocationDevice,
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
                    onTranscribeAudio = { fileName, mimeType, audioBytes, autoSend ->
                        sessionViewModel.transcribeRecordedAudio(
                            fileName = fileName,
                            mimeType = mimeType,
                            audioBytes = audioBytes,
                            autoSend = autoSend,
                        )
                    },
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
