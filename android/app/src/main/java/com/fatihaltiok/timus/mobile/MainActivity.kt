package com.fatihaltiok.timus.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.fatihaltiok.timus.mobile.ui.TimusMobileApp
import com.fatihaltiok.timus.mobile.ui.theme.TimusTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TimusTheme {
                TimusMobileApp()
            }
        }
    }
}
