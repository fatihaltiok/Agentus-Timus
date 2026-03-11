package com.fatihaltiok.timus.mobile.ui

import androidx.compose.runtime.saveable.Saver
import com.fatihaltiok.timus.mobile.data.TimusConfig

val TimusConfigSaver: Saver<TimusConfig, List<String>> = Saver(
    save = { config ->
        listOf(config.baseUrl, config.username, config.password)
    },
    restore = { raw ->
        TimusConfig(
            baseUrl = raw.getOrNull(0).orEmpty(),
            username = raw.getOrNull(1).orEmpty(),
            password = raw.getOrNull(2).orEmpty(),
        )
    },
)
