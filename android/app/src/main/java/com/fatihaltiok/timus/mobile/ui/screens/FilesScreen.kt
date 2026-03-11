package com.fatihaltiok.timus.mobile.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.fatihaltiok.timus.mobile.ui.components.TimusCard

@Composable
fun FilesScreen() {
    Column(modifier = Modifier.padding(vertical = 8.dp)) {
        TimusCard(
            title = "Dateien",
            subtitle = "Upload, Download, Öffnen und Teilen werden hier zusammengeführt.",
        )
        TimusCard(
            title = "Geplante Aktionen",
            subtitle = "Datei auswählen · Upload an Timus · Ergebnis öffnen · Per Android teilen",
        )
        Text(
            text = "Phase A legt nur die Dateiverwaltungsfläche an. Der echte Picker- und Download-Flow folgt in Phase C.",
            modifier = Modifier.padding(horizontal = 22.dp, vertical = 12.dp),
        )
    }
}
