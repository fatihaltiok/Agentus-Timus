package com.fatihaltiok.timus.mobile.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.Code
import androidx.compose.material.icons.outlined.DataObject
import androidx.compose.material.icons.outlined.Image
import androidx.compose.material.icons.outlined.MyLocation
import androidx.compose.material.icons.outlined.Memory
import androidx.compose.material.icons.outlined.Psychology
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.SettingsSuggest
import androidx.compose.material.icons.outlined.Terminal
import androidx.compose.material3.TextButton
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fatihaltiok.timus.mobile.data.SessionSummary
import com.fatihaltiok.timus.mobile.model.LocationUiState
import com.fatihaltiok.timus.mobile.ui.components.TimusCard
import com.fatihaltiok.timus.mobile.ui.components.VoiceOrb
import com.fatihaltiok.timus.mobile.ui.theme.GlowAccent
import com.fatihaltiok.timus.mobile.ui.theme.GlowPrimary
import com.fatihaltiok.timus.mobile.ui.theme.Night1
import com.fatihaltiok.timus.mobile.ui.theme.Panel
import com.fatihaltiok.timus.mobile.ui.theme.PanelBorder
import com.fatihaltiok.timus.mobile.ui.theme.PanelBorderBright
import com.fatihaltiok.timus.mobile.ui.theme.PanelStrong
import com.fatihaltiok.timus.mobile.ui.theme.TextMuted
import com.fatihaltiok.timus.mobile.ui.theme.TextSoft
import com.fatihaltiok.timus.mobile.ui.theme.TextStrong
import com.fatihaltiok.timus.mobile.ui.theme.TimusAccent
import com.fatihaltiok.timus.mobile.ui.theme.TimusIdle
import com.fatihaltiok.timus.mobile.ui.theme.TimusOk
import com.fatihaltiok.timus.mobile.ui.theme.TimusPrimary
import com.fatihaltiok.timus.mobile.ui.theme.TimusPrimarySoft
import com.fatihaltiok.timus.mobile.ui.theme.statusColorFor

private data class AgentOrbitNode(
    val label: String,
    val icon: ImageVector,
    val x: Int,
    val y: Int,
    val active: Boolean = false,
)

private val orbitNodes = listOf(
    AgentOrbitNode("image", Icons.Outlined.Image, -116, -32),
    AgentOrbitNode("executor", Icons.Outlined.Memory, 0, -102),
    AgentOrbitNode("research", Icons.Outlined.Search, 116, -28),
    AgentOrbitNode("reasoning", Icons.Outlined.Psychology, 126, 58),
    AgentOrbitNode("creative", Icons.Outlined.SettingsSuggest, 98, 142, active = true),
    AgentOrbitNode("development", Icons.Outlined.Code, 48, 226),
    AgentOrbitNode("data", Icons.Outlined.DataObject, -24, 256),
    AgentOrbitNode("communication", Icons.Outlined.ChatBubbleOutline, -108, 208),
    AgentOrbitNode("system", Icons.Outlined.SettingsSuggest, -144, 112),
    AgentOrbitNode("shell", Icons.Outlined.Terminal, -138, 34),
)

@Composable
fun HomeScreen(
    summary: SessionSummary,
    voiceState: String,
    locationState: LocationUiState,
    onRefreshLocation: () -> Unit,
) {
    val scoreText = String.format("%.1f", summary.autonomyScore * 10)
    Column(
        modifier = Modifier
            .verticalScroll(rememberScrollState())
            .padding(top = 8.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TimusCanvasHero(
            summary = summary,
            voiceState = voiceState,
        )

        TimusCard(
            title = "Session",
            subtitle = "Timus Session Canvas\n• 2 active sessions",
            status = if (summary.activeAlerts > 0) "warning" else "ok",
        )

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            TimusMiniStatCard(
                modifier = Modifier.weight(1f),
                title = scoreText,
                subtitle = "Autonomy Score",
                status = if (summary.activeAlerts > 0) "warning" else summary.serviceState,
                trailing = {
                    VoiceOrb(state = voiceState, size = 18.dp)
                },
            )
            TimusMiniStatCard(
                modifier = Modifier.weight(1f),
                title = if (summary.activeAlerts > 0) "WARN" else "RECENT",
                subtitle = "Systemlage",
                status = if (summary.activeAlerts > 0) "warning" else "idle",
            )
        }

        TimusCard(
            title = "TXMS Session 02.json",
            subtitle = "Heute, 09:41\nLetzte Session · Gestern, 16:05",
            status = "idle",
        )

        TimusCard(
            title = "Standort",
            subtitle = buildLocationSubtitle(locationState),
            status = locationStatus(locationState),
            trailing = {
                TextButton(onClick = onRefreshLocation) {
                    Icon(
                        imageVector = Icons.Outlined.MyLocation,
                        contentDescription = "Standort aktualisieren",
                        tint = TimusPrimary,
                        modifier = Modifier.size(16.dp),
                    )
                    Text(
                        text = if (locationState.lastResolvedLocation == null) "Abrufen" else "Aktualisieren",
                        color = TimusPrimary,
                        modifier = Modifier.padding(start = 6.dp),
                    )
                }
            },
        )
    }
}

@Composable
private fun TimusCanvasHero(
    summary: SessionSummary,
    voiceState: String,
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp)
            .clip(RoundedCornerShape(32.dp))
            .background(
                Brush.verticalGradient(
                    colors = listOf(PanelStrong, Night1, Panel),
                ),
            )
            .border(1.dp, PanelBorder.copy(alpha = 0.75f), RoundedCornerShape(32.dp))
            .padding(horizontal = 16.dp, vertical = 18.dp),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TinyTopButton("☰")
                Text(
                    text = "· TIMUS CANVAS ·",
                    color = TimusPrimary,
                    fontWeight = FontWeight.SemiBold,
                )
                TinyTopButton("⌕")
            }

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 18.dp)
                    .size(360.dp),
                contentAlignment = Alignment.Center,
            ) {
                OrbitRings()
                orbitNodes.forEach { node ->
                    OrbitNode(node = node)
                }
                MetaCore(voiceState = voiceState)
            }

            Text(
                text = "Service ${summary.serviceState} · Alerts ${summary.activeAlerts}",
                color = statusColorFor(if (summary.activeAlerts > 0) "warning" else summary.serviceState),
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}

@Composable
private fun OrbitRings() {
    Box(contentAlignment = Alignment.Center) {
        listOf(270.dp, 216.dp, 164.dp, 112.dp).forEachIndexed { index, size ->
            Box(
                modifier = Modifier
                    .size(size)
                    .clip(CircleShape)
                    .border(
                        width = if (index == 0) 1.dp else 0.8.dp,
                        color = if (index % 2 == 0) PanelBorder.copy(alpha = 0.55f) else PanelBorderBright.copy(alpha = 0.22f),
                        shape = CircleShape,
                    ),
            )
        }
        Box(
            modifier = Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(TimusPrimary.copy(alpha = 0.55f)),
        )
    }
}

@Composable
private fun MetaCore(voiceState: String) {
    Box(
        modifier = Modifier
            .size(108.dp)
            .clip(CircleShape)
            .background(GlowPrimary.copy(alpha = 0.20f)),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .size(82.dp)
                .clip(CircleShape)
                .background(
                    Brush.radialGradient(
                        colors = listOf(TimusPrimary, TimusAccent),
                    ),
                )
                .border(1.dp, TimusPrimarySoft.copy(alpha = 0.55f), CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("meta", color = TextStrong, fontWeight = FontWeight.Bold)
                VoiceOrb(
                    state = voiceState,
                    size = 8.dp,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
        }
    }
}

@Composable
private fun OrbitNode(node: AgentOrbitNode) {
    Box(
        modifier = Modifier
            .offset(node.x.dp, node.y.dp)
            .size(if (node.active) 72.dp else 68.dp)
            .clip(CircleShape)
            .background(
                if (node.active) GlowPrimary.copy(alpha = 0.18f) else Panel.copy(alpha = 0.85f),
            )
            .border(
                1.dp,
                if (node.active) TimusOk.copy(alpha = 0.85f) else PanelBorder.copy(alpha = 0.70f),
                CircleShape,
            ),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(
                imageVector = node.icon,
                contentDescription = node.label,
                tint = if (node.active) TimusOk else TextMuted,
                modifier = Modifier.size(22.dp),
            )
            Text(
                text = node.label,
                color = if (node.active) TimusOk else TextSoft,
                fontSize = 11.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}

@Composable
private fun TinyTopButton(label: String) {
    Box(
        modifier = Modifier
            .size(34.dp)
            .clip(CircleShape)
            .background(Panel.copy(alpha = 0.85f))
            .border(1.dp, PanelBorder.copy(alpha = 0.70f), CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = TextMuted, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun TimusMiniStatCard(
    modifier: Modifier = Modifier,
    title: String,
    subtitle: String,
    status: String,
    trailing: @Composable (() -> Unit)? = null,
) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(22.dp))
            .background(
                Brush.linearGradient(
                    colors = listOf(PanelStrong, Panel),
                ),
            )
            .border(1.dp, PanelBorder.copy(alpha = 0.65f), RoundedCornerShape(22.dp))
            .padding(horizontal = 16.dp, vertical = 14.dp),
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = title,
                    color = statusColorFor(status),
                    fontWeight = FontWeight.Bold,
                    fontSize = 22.sp,
                )
                trailing?.invoke()
            }
            Text(
                text = subtitle,
                color = TextMuted,
                modifier = Modifier.padding(top = 6.dp),
            )
        }
    }
}

private fun buildLocationSubtitle(locationState: LocationUiState): String {
    val resolved = locationState.lastResolvedLocation
    val accuracy = resolved?.accuracyMeters?.let { "Genauigkeit ±${it.toInt()} m" }
    val capturedAt = resolved?.capturedAt
        ?.replace("T", " ")
        ?.removeSuffix("Z")
        ?.take(16)
        ?.let { "Zuletzt: $it" }

    return buildList {
        add(locationState.statusMessage)
        if (!accuracy.isNullOrBlank()) add(accuracy)
        if (!capturedAt.isNullOrBlank()) add(capturedAt)
        if (!resolved?.mapsUrl.isNullOrBlank()) add("Google Maps bereit")
        if (!locationState.error.isNullOrBlank()) add("Fehler: ${locationState.error}")
    }.joinToString("\n")
}

private fun locationStatus(locationState: LocationUiState): String =
    when (locationState.state.lowercase()) {
        "ready" -> "ok"
        "warning", "requesting_permission", "fetching", "syncing" -> "warning"
        "error", "denied" -> "error"
        else -> "idle"
    }
