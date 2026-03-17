package com.fatihaltiok.timus.mobile.location

private const val DEFAULT_FOREGROUND_AUTO_SYNC_INTERVAL_MS = 60 * 1000L
private const val DEFAULT_STALE_RETRY_INTERVAL_MS = 20 * 1000L
private const val DEFAULT_NAVIGATION_AUTO_SYNC_INTERVAL_MS = 20 * 1000L
private const val DEFAULT_NAVIGATION_STALE_RETRY_INTERVAL_MS = 10 * 1000L

data class LocationAutoSyncDecision(
    val shouldSync: Boolean,
    val reason: String,
    val nextDelayMs: Long,
)

private fun normalizePresenceStatus(value: String?): String =
    when (value?.trim()?.lowercase()) {
        "live", "recent", "stale", "unknown" -> value.trim().lowercase()
        else -> "unknown"
    }

fun evaluateForegroundLocationAutoSync(
    authenticated: Boolean,
    permissionGranted: Boolean,
    currentState: String,
    presenceStatus: String?,
    lastAttemptEpochMs: Long?,
    nowEpochMs: Long,
    navigationModeActive: Boolean = false,
    intervalMs: Long = DEFAULT_FOREGROUND_AUTO_SYNC_INTERVAL_MS,
    staleRetryIntervalMs: Long = DEFAULT_STALE_RETRY_INTERVAL_MS,
    navigationIntervalMs: Long = DEFAULT_NAVIGATION_AUTO_SYNC_INTERVAL_MS,
    navigationStaleRetryIntervalMs: Long = DEFAULT_NAVIGATION_STALE_RETRY_INTERVAL_MS,
): LocationAutoSyncDecision {
    if (!authenticated) {
        return LocationAutoSyncDecision(false, "not_authenticated", intervalMs)
    }
    if (!permissionGranted) {
        return LocationAutoSyncDecision(false, "permission_missing", intervalMs)
    }

    val normalizedState = currentState.trim().lowercase()
    if (normalizedState == "fetching" || normalizedState == "syncing") {
        return LocationAutoSyncDecision(false, "sync_in_flight", staleRetryIntervalMs)
    }

    val normalizedPresence = normalizePresenceStatus(presenceStatus)
    val effectiveIntervalMs = if (navigationModeActive) navigationIntervalMs else intervalMs
    val effectiveRetryMs = if (navigationModeActive) navigationStaleRetryIntervalMs else staleRetryIntervalMs
    val safeInterval = effectiveIntervalMs.coerceAtLeast(15_000L)
    val safeRetry = effectiveRetryMs.coerceAtLeast(10_000L)
    val lastAttempt = lastAttemptEpochMs ?: 0L
    val elapsed = (nowEpochMs - lastAttempt).coerceAtLeast(0L)

    if (lastAttemptEpochMs == null) {
        return LocationAutoSyncDecision(true, "initial_sync", 0L)
    }

    if (normalizedPresence == "stale" || normalizedPresence == "unknown") {
        if (elapsed >= safeRetry) {
            return LocationAutoSyncDecision(
                true,
                if (navigationModeActive) "navigation_stale_or_unknown_presence" else "stale_or_unknown_presence",
                0L,
            )
        }
        return LocationAutoSyncDecision(false, "stale_retry_not_due", safeRetry - elapsed)
    }

    if (elapsed >= safeInterval) {
        return LocationAutoSyncDecision(
            true,
            if (navigationModeActive) "navigation_interval_elapsed" else "interval_elapsed",
            0L,
        )
    }

    return LocationAutoSyncDecision(false, "interval_not_elapsed", safeInterval - elapsed)
}
