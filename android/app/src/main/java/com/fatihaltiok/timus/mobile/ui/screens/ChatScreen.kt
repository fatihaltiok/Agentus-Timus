package com.fatihaltiok.timus.mobile.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.fatihaltiok.timus.mobile.model.ChatMessage
import com.fatihaltiok.timus.mobile.ui.components.TimusCard
import com.fatihaltiok.timus.mobile.ui.theme.Night0
import com.fatihaltiok.timus.mobile.ui.theme.PanelStrong
import com.fatihaltiok.timus.mobile.ui.theme.TimusPrimary

@Composable
fun ChatScreen(
    messages: List<ChatMessage>,
    draft: String,
    loading: Boolean,
    error: String?,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(vertical = 8.dp),
    ) {
        TimusCard(
            title = "Chat",
            subtitle = "Voice-first Verlauf mit Text-Fallback und Live-Antworten.",
            status = "idle",
        )
        if (!error.isNullOrBlank()) {
            TimusCard(
                title = "Fehler",
                subtitle = error,
                status = "error",
            )
        }
        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
        ) {
            items(messages) { message ->
                TimusCard(
                    title = if (message.role == "user") "Du" else (message.agent ?: "Timus"),
                    subtitle = message.text,
                    status = if (message.role == "user") "idle" else "ok",
                )
            }
        }
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            OutlinedTextField(
                value = draft,
                onValueChange = onDraftChange,
                label = { Text("Nachricht an Timus") },
                modifier = Modifier.weight(1f),
                maxLines = 4,
            )
            Button(
                onClick = onSend,
                enabled = draft.isNotBlank() && !loading,
                shape = RoundedCornerShape(18.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = TimusPrimary,
                    contentColor = Night0,
                    disabledContainerColor = PanelStrong,
                ),
            ) {
                if (loading) {
                    CircularProgressIndicator(
                        modifier = Modifier.padding(2.dp),
                        strokeWidth = 2.dp,
                    )
                } else {
                    Text("Senden", fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}
