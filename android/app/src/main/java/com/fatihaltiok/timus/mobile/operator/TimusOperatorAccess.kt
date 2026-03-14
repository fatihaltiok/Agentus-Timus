package com.fatihaltiok.timus.mobile.operator

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.provider.Settings
import java.time.Instant

data class TimusOperatorStatus(
    val accessibilityEnabled: Boolean,
    val lastPackageName: String = "",
    val lastClassName: String = "",
    val lastEventType: String = "",
    val lastSeenAt: String = "",
) {
    val state: String
        get() = if (accessibilityEnabled) "ok" else "warning"

    val summary: String
        get() = if (!accessibilityEnabled) {
            "Accessibility-Zugriff ist noch nicht freigegeben."
        } else {
            buildString {
                append("Android-Operator aktiv")
                if (lastPackageName.isNotBlank()) {
                    append("\nApp: ")
                    append(lastPackageName)
                }
                if (lastClassName.isNotBlank()) {
                    append("\nView: ")
                    append(lastClassName)
                }
                if (lastEventType.isNotBlank()) {
                    append("\nLetztes Event: ")
                    append(lastEventType)
                }
                if (lastSeenAt.isNotBlank()) {
                    append("\nZuletzt gesehen: ")
                    append(lastSeenAt.replace("T", " ").removeSuffix("Z").take(19))
                }
            }
        }
}

class TimusOperatorAccess(
    private val context: Context,
) {

    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun readStatus(): TimusOperatorStatus =
        TimusOperatorStatus(
            accessibilityEnabled = isAccessibilityEnabled(),
            lastPackageName = prefs.getString(KEY_LAST_PACKAGE, "").orEmpty(),
            lastClassName = prefs.getString(KEY_LAST_CLASS, "").orEmpty(),
            lastEventType = prefs.getString(KEY_LAST_EVENT, "").orEmpty(),
            lastSeenAt = prefs.getString(KEY_LAST_SEEN_AT, "").orEmpty(),
        )

    fun openAccessibilitySettings() {
        val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        appContext.startActivity(intent)
    }

    fun clearRuntimeSnapshot() {
        prefs.edit()
            .remove(KEY_LAST_PACKAGE)
            .remove(KEY_LAST_CLASS)
            .remove(KEY_LAST_EVENT)
            .remove(KEY_LAST_SEEN_AT)
            .apply()
    }

    private fun isAccessibilityEnabled(): Boolean {
        val enabledServices = Settings.Secure.getString(
            appContext.contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
        ).orEmpty()
        return enabledServices.contains(serviceComponentName().flattenToString(), ignoreCase = true)
    }

    private fun serviceComponentName(): ComponentName =
        ComponentName(appContext, TimusAccessibilityService::class.java)

    companion object {
        const val PREFS_NAME = "timus_operator_access"
        const val KEY_LAST_PACKAGE = "last_package"
        const val KEY_LAST_CLASS = "last_class"
        const val KEY_LAST_EVENT = "last_event"
        const val KEY_LAST_SEEN_AT = "last_seen_at"

        fun markEvent(
            context: Context,
            packageName: CharSequence?,
            className: CharSequence?,
            eventType: String,
        ) {
            context.applicationContext
                .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_LAST_PACKAGE, packageName?.toString().orEmpty())
                .putString(KEY_LAST_CLASS, className?.toString().orEmpty())
                .putString(KEY_LAST_EVENT, eventType)
                .putString(KEY_LAST_SEEN_AT, Instant.now().toString())
                .apply()
        }
    }
}
