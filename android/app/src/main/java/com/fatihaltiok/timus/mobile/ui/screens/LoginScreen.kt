package com.fatihaltiok.timus.mobile.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.fatihaltiok.timus.mobile.data.TimusConfig
import com.fatihaltiok.timus.mobile.ui.theme.Night0
import com.fatihaltiok.timus.mobile.ui.theme.PanelStrong
import com.fatihaltiok.timus.mobile.ui.theme.TextMuted
import com.fatihaltiok.timus.mobile.ui.theme.TimusPrimary

@Composable
fun LoginScreen(
    initialConfig: TimusConfig,
    onLogin: (TimusConfig) -> Unit,
) {
    val baseUrl = remember { mutableStateOf(initialConfig.baseUrl) }
    val username = remember { mutableStateOf(initialConfig.username) }
    val password = remember { mutableStateOf(initialConfig.password) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = "Timus Mobile",
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = "Voice-first Zugang zu Timus mit voller Admin-Kontrolle",
            color = TextMuted,
            modifier = Modifier.padding(top = 10.dp, bottom = 24.dp),
        )

        OutlinedTextField(
            value = baseUrl.value,
            onValueChange = { baseUrl.value = it },
            label = { Text("Base URL") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        Spacer(modifier = Modifier.height(12.dp))
        OutlinedTextField(
            value = username.value,
            onValueChange = { username.value = it },
            label = { Text("Benutzername") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        Spacer(modifier = Modifier.height(12.dp))
        OutlinedTextField(
            value = password.value,
            onValueChange = { password.value = it },
            label = { Text("Passwort") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
        )
        Spacer(modifier = Modifier.height(20.dp))
        Button(
            onClick = {
                onLogin(
                    TimusConfig(
                        baseUrl = baseUrl.value.trim(),
                        username = username.value.trim(),
                        password = password.value,
                    ),
                )
            },
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(20.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = TimusPrimary,
                contentColor = Night0,
                disabledContainerColor = PanelStrong,
            ),
        ) {
            Text("In die Konsole")
        }
    }
}
