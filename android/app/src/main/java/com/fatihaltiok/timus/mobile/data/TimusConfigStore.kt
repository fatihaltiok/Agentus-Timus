package com.fatihaltiok.timus.mobile.data

import android.content.Context

class TimusConfigStore(
    context: Context,
) {

    private val prefs = context.applicationContext.getSharedPreferences(
        "timus_mobile_config",
        Context.MODE_PRIVATE,
    )

    fun load(): TimusConfig? {
        if (!prefs.getBoolean(KEY_PRESENT, false)) {
            return null
        }
        return TimusConfig(
            baseUrl = prefs.getString(KEY_BASE_URL, TimusConfig().baseUrl).orEmpty(),
            username = prefs.getString(KEY_USERNAME, "").orEmpty(),
            password = prefs.getString(KEY_PASSWORD, "").orEmpty(),
            inputLanguage = prefs.getString(KEY_INPUT_LANGUAGE, "de").orEmpty().ifBlank { "de" },
            responseLanguage = prefs.getString(KEY_RESPONSE_LANGUAGE, "de").orEmpty().ifBlank { "de" },
        )
    }

    fun save(config: TimusConfig) {
        prefs.edit()
            .putBoolean(KEY_PRESENT, true)
            .putString(KEY_BASE_URL, config.baseUrl.trim())
            .putString(KEY_USERNAME, config.username.trim())
            .putString(KEY_PASSWORD, config.password)
            .putString(KEY_INPUT_LANGUAGE, config.inputLanguage)
            .putString(KEY_RESPONSE_LANGUAGE, config.responseLanguage)
            .apply()
    }

    fun clear() {
        prefs.edit()
            .remove(KEY_PRESENT)
            .remove(KEY_BASE_URL)
            .remove(KEY_USERNAME)
            .remove(KEY_PASSWORD)
            .remove(KEY_INPUT_LANGUAGE)
            .remove(KEY_RESPONSE_LANGUAGE)
            .apply()
    }

    companion object {
        private const val KEY_PRESENT = "present"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_USERNAME = "username"
        private const val KEY_PASSWORD = "password"
        private const val KEY_INPUT_LANGUAGE = "input_language"
        private const val KEY_RESPONSE_LANGUAGE = "response_language"
    }
}
