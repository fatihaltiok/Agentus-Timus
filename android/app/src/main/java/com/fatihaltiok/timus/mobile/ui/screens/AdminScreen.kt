package com.fatihaltiok.timus.mobile.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.fatihaltiok.timus.mobile.operator.TimusOperatorAccess
import com.fatihaltiok.timus.mobile.ui.components.TimusCard
import com.fatihaltiok.timus.mobile.ui.theme.TimusPrimary

@Composable
fun AdminScreen() {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val operatorAccess = remember(context) { TimusOperatorAccess(context) }
    var operatorStatus by remember { mutableStateOf(operatorAccess.readStatus()) }

    DisposableEffect(lifecycleOwner, operatorAccess) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                operatorStatus = operatorAccess.readStatus()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }

    Column(
        modifier = Modifier.padding(vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        TimusCard(
            title = "Admin",
            subtitle = "Services, Gates, Incidents, Kosten und Diagnoseaktionen.",
        )
        TimusCard(
            title = "Android Operator",
            subtitle = operatorStatus.summary,
            status = operatorStatus.state,
            trailing = {
                TextButton(onClick = {
                    operatorAccess.openAccessibilitySettings()
                }) {
                    Text(
                        text = if (operatorStatus.accessibilityEnabled) "Einstellungen" else "Freigeben",
                        color = TimusPrimary,
                    )
                }
            },
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
