package com.fatihaltiok.timus.mobile.ui.components

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavHostController
import androidx.navigation.compose.currentBackStackEntryAsState
import com.fatihaltiok.timus.mobile.model.AppDestination
import com.fatihaltiok.timus.mobile.ui.theme.GlowAccent
import com.fatihaltiok.timus.mobile.ui.theme.GlowError
import com.fatihaltiok.timus.mobile.ui.theme.GlowPrimary
import com.fatihaltiok.timus.mobile.ui.theme.GlowWarn
import com.fatihaltiok.timus.mobile.ui.theme.Night0
import com.fatihaltiok.timus.mobile.ui.theme.Night1
import com.fatihaltiok.timus.mobile.ui.theme.Night2
import com.fatihaltiok.timus.mobile.ui.theme.Panel
import com.fatihaltiok.timus.mobile.ui.theme.PanelBorder
import com.fatihaltiok.timus.mobile.ui.theme.PanelBorderBright
import com.fatihaltiok.timus.mobile.ui.theme.PanelMuted
import com.fatihaltiok.timus.mobile.ui.theme.PanelStrong
import com.fatihaltiok.timus.mobile.ui.theme.TextMuted
import com.fatihaltiok.timus.mobile.ui.theme.TextSoft
import com.fatihaltiok.timus.mobile.ui.theme.TimusError
import com.fatihaltiok.timus.mobile.ui.theme.TimusOk
import com.fatihaltiok.timus.mobile.ui.theme.TimusPrimary
import com.fatihaltiok.timus.mobile.ui.theme.TimusWarn
import com.fatihaltiok.timus.mobile.ui.theme.statusColorFor

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
                containerColor = PanelMuted,
                tonalElevation = 0.dp,
                modifier = Modifier
                    .padding(horizontal = 14.dp, vertical = 10.dp)
                    .clip(RoundedCornerShape(28.dp))
                    .border(
                        width = 1.dp,
                        color = PanelBorder,
                        shape = RoundedCornerShape(28.dp),
                    ),
            ) {
                val navBackStackEntry = navController.currentBackStackEntryAsState().value
                val destination = navBackStackEntry?.destination
                AppDestination.bottomBarItems.forEach { item ->
                    val selected = destination?.hierarchy?.any { it.route == item.route } == true
                    NavigationBarItem(
                        selected = selected,
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
                        label = {
                            Text(
                                item.label,
                                fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                            )
                        },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = TimusPrimary,
                            selectedTextColor = TimusPrimary,
                            indicatorColor = GlowAccent,
                            unselectedIconColor = TextSoft,
                            unselectedTextColor = TextSoft,
                        ),
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
                        colors = listOf(Night0, Night1, Night2),
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
    val statusColor = statusColorFor(voiceState)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 14.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column {
            Text(
                text = "TIMUS",
                fontWeight = FontWeight.Bold,
                color = TimusPrimary,
            )
            Text(
                text = "Mobile Console",
                color = TextMuted,
            )
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            VoiceOrb(state = voiceState, size = 20.dp)
            Text(
                text = voiceState.uppercase(),
                modifier = Modifier.padding(start = 10.dp),
                color = statusColor,
                fontWeight = FontWeight.Medium,
            )
        }
    }
}

@Composable
fun VoiceOrb(
    state: String,
    modifier: Modifier = Modifier,
    size: androidx.compose.ui.unit.Dp = 18.dp,
) {
    val color = statusColorFor(state)
    val outerGlow = when (state.lowercase()) {
        "error" -> GlowError
        "warning", "warn", "transcribing" -> GlowWarn
        "speaking", "listening", "thinking" -> GlowPrimary
        else -> GlowAccent
    }
    val pulseDuration = when (state.lowercase()) {
        "listening" -> 900
        "speaking" -> 800
        "thinking" -> 1200
        "error" -> 1100
        else -> 1800
    }
    val pulseRange = when (state.lowercase()) {
        "listening" -> 1.28f
        "speaking" -> 1.22f
        "thinking" -> 1.15f
        "error" -> 1.12f
        else -> 1.06f
    }
    val transition = rememberInfiniteTransition(label = "voice_orb")
    val pulse by transition.animateFloat(
        initialValue = 0.92f,
        targetValue = pulseRange,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = pulseDuration),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "voice_orb_scale",
    )
    val haloAlpha by transition.animateFloat(
        initialValue = 0.22f,
        targetValue = 0.65f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = pulseDuration),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "voice_orb_alpha",
    )

    Box(
        modifier = modifier.size(size * 2.2f),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .size(size * 2f)
                .scale(pulse)
                .alpha(haloAlpha)
                .clip(CircleShape)
                .background(outerGlow),
        )
        Box(
            modifier = Modifier
                .size(size * 1.45f)
                .clip(CircleShape)
                .background(color.copy(alpha = 0.25f)),
        )
        Box(
            modifier = Modifier
                .size(size)
                .clip(CircleShape)
                .background(color),
        )
    }
}

@Composable
fun TimusCard(
    title: String,
    subtitle: String,
    modifier: Modifier = Modifier,
    status: String = "idle",
    trailing: @Composable (() -> Unit)? = null,
) {
    val statusColor = statusColorFor(status)
    val borderColor = when (status.lowercase()) {
        "error", "failed", "blocked" -> TimusError
        "warning", "warn", "degraded", "transcribing" -> TimusWarn
        "ok", "healthy", "completed", "success", "speaking" -> TimusOk
        else -> PanelBorderBright
    }
    Box(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .clip(RoundedCornerShape(24.dp))
            .background(
                Brush.linearGradient(
                    colors = listOf(PanelStrong, Panel),
                ),
            )
            .border(1.dp, borderColor.copy(alpha = 0.55f), RoundedCornerShape(24.dp))
            .padding(18.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(10.dp)
                            .clip(CircleShape)
                            .background(statusColor),
                    )
                    Text(
                        text = title,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(start = 10.dp),
                    )
                }
                Text(
                    text = subtitle,
                    color = TextMuted,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
            trailing?.invoke()
        }
    }
}
