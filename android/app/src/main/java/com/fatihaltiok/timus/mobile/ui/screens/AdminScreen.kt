package com.fatihaltiok.timus.mobile.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.fatihaltiok.timus.mobile.ui.components.TimusCard

@Composable
fun AdminScreen() {
    Column(modifier = Modifier.padding(vertical = 8.dp)) {
        TimusCard(
            title = "Admin",
            subtitle = "Services, Gates, Incidents, Kosten und Diagnoseaktionen.",
        )
        TimusCard(
            title = "MCP / Dispatcher",
            subtitle = "Health, Restart, Status und Runtime-Gates werden hier angezeigt.",
        )
        TimusCard(
            title = "API & Kosten",
            subtitle = "Provider, aktive API-Zugänge, 24h-Kosten und Budgetlage.",
        )
    }
}
