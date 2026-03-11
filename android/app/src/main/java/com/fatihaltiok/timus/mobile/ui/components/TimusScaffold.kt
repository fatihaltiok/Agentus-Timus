package com.fatihaltiok.timus.mobile.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavHostController
import androidx.navigation.compose.currentBackStackEntryAsState
import com.fatihaltiok.timus.mobile.model.AppDestination
import com.fatihaltiok.timus.mobile.ui.theme.Glow
import com.fatihaltiok.timus.mobile.ui.theme.Night0
import com.fatihaltiok.timus.mobile.ui.theme.Night1
import com.fatihaltiok.timus.mobile.ui.theme.Panel
import com.fatihaltiok.timus.mobile.ui.theme.TextMuted

@Composable
fun TimusScaffold(
    navController: NavHostController,
    voiceState: String,
    content: @Composable () -> Unit,
) {
    Scaffold(
        topBar = { TimusTopBar(voiceState = voiceState) },
        bottomBar = {
            NavigationBar(
                containerColor = Panel,
                tonalElevation = 0.dp,
            ) {
                val navBackStackEntry = navController.currentBackStackEntryAsState().value
                val destination = navBackStackEntry?.destination
                AppDestination.bottomBarItems.forEach { item ->
                    NavigationBarItem(
                        selected = destination?.hierarchy?.any { it.route == item.route } == true,
                        onClick = {
                            navController.navigate(item.route) {
                                popUpTo(navController.graph.startDestinationId) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(imageVector = item.icon, contentDescription = item.label) },
                        label = { Text(item.label) },
                    )
                }
            }
        },
        containerColor = Night0,
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .background(
                    Brush.verticalGradient(
                        colors = listOf(Night0, Night1),
                    ),
                )
                .padding(innerPadding),
        ) {
            content()
        }
    }
}

@Composable
private fun TimusTopBar(voiceState: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 14.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column {
            Text(
                text = "TIMUS MOBILE",
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = "Voice-first Control",
                color = TextMuted,
            )
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            VoiceOrb(state = voiceState)
            Text(
                text = voiceState.uppercase(),
                modifier = Modifier.padding(start = 10.dp),
                color = TextMuted,
            )
        }
    }
}

@Composable
fun VoiceOrb(
    state: String,
    modifier: Modifier = Modifier,
) {
    val glowAlpha = when (state) {
        "listening" -> 1.0f
        "thinking" -> 0.8f
        "speaking" -> 0.95f
        "error" -> 0.45f
        else -> 0.65f
    }
    androidx.compose.foundation.layout.Box(
        modifier = modifier
            .size(18.dp)
            .clip(CircleShape)
            .background(Glow.copy(alpha = glowAlpha)),
    )
}

@Composable
fun TimusCard(
    title: String,
    subtitle: String,
    modifier: Modifier = Modifier,
    trailing: @Composable (() -> Unit)? = null,
) {
    androidx.compose.foundation.layout.Box(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .clip(RoundedCornerShape(22.dp))
            .background(Panel)
            .padding(18.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = title, fontWeight = FontWeight.SemiBold)
                Text(text = subtitle, color = TextMuted, modifier = Modifier.padding(top = 6.dp))
            }
            trailing?.invoke()
        }
    }
}
