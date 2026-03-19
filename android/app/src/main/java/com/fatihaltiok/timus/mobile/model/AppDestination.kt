package com.fatihaltiok.timus.mobile.model

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.ui.graphics.vector.ImageVector

sealed class AppDestination(
    val route: String,
    val label: String,
    val icon: ImageVector,
) {
    object Home : AppDestination("home", "Home", Icons.Outlined.Home)
    object Navigation : AppDestination("navigation", "Karte", Icons.Outlined.Map)
    object Chat : AppDestination("chat", "Chat", Icons.Outlined.ChatBubbleOutline)
    object Voice : AppDestination("voice", "Voice", Icons.Outlined.Mic)
    object Files : AppDestination("files", "Dateien", Icons.Outlined.FolderOpen)
    object Admin : AppDestination("admin", "Admin", Icons.Outlined.Settings)

    companion object {
        fun bottomBarItems(): List<AppDestination> =
            listOf(Home, Navigation, Chat, Voice, Files, Admin)
    }
}
