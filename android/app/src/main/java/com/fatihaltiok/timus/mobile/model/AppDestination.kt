package com.fatihaltiok.timus.mobile.model

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.ui.graphics.vector.ImageVector

sealed class AppDestination(
    val route: String,
    val label: String,
    val icon: ImageVector,
) {
    data object Home : AppDestination("home", "Home", Icons.Outlined.Home)
    data object Chat : AppDestination("chat", "Chat", Icons.Outlined.ChatBubbleOutline)
    data object Voice : AppDestination("voice", "Voice", Icons.Outlined.Mic)
    data object Files : AppDestination("files", "Dateien", Icons.Outlined.FolderOpen)
    data object Admin : AppDestination("admin", "Admin", Icons.Outlined.Settings)

    companion object {
        val bottomBarItems = listOf(Home, Chat, Voice, Files, Admin)
    }
}
