package com.fatihaltiok.timus.mobile.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.fatihaltiok.timus.mobile.data.SessionSummary
import com.fatihaltiok.timus.mobile.ui.components.TimusCard
import com.fatihaltiok.timus.mobile.ui.theme.Glow
import com.fatihaltiok.timus.mobile.ui.theme.Panel
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size

@Composable
fun HomeScreen(
    summary: SessionSummary,
    voiceState: String,
) {
    Column(modifier = Modifier.padding(vertical = 8.dp)) {
        TimusCard(
            title = "Autonomy Score ${summary.autonomyScore}",
            subtitle = "Service ${summary.serviceState} · Alerts ${summary.activeAlerts}",
        )
        TimusCard(
            title = "Voice Priority",
            subtitle = "Zustand: $voiceState · Bereit: ${summary.voiceReady}",
            trailing = {
                Box(
                    modifier = Modifier
                        .size(56.dp)
                        .clip(CircleShape)
                        .background(Glow.copy(alpha = 0.22f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Box(
                        modifier = Modifier
                            .size(22.dp)
                            .clip(CircleShape)
                            .background(Glow),
                    )
                }
            },
        )
        TimusCard(
            title = "Agent Canvas",
            subtitle = "Meta im Zentrum, Voice-first mobile control, Admin komplett in der App.",
        )
        Text(
            text = "Phase A liefert nur das Grundgerüst. Chat, Voice, Dateien und Admin werden danach an die echten Endpunkte angebunden.",
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 22.dp, vertical = 12.dp),
            fontWeight = FontWeight.Medium,
        )
    }
}
