package com.fatihaltiok.timus.mobile.location

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocationAutoSyncPolicyTest {

    @Test
    fun `initial sync runs immediately when authenticated and permitted`() {
        val decision = evaluateForegroundLocationAutoSync(
            authenticated = true,
            permissionGranted = true,
            currentState = "idle",
            presenceStatus = "unknown",
            lastAttemptEpochMs = null,
            nowEpochMs = 1_000L,
        )

        assertTrue(decision.shouldSync)
        assertEquals("initial_sync", decision.reason)
    }

    @Test
    fun `stale presence retries before full interval`() {
        val decision = evaluateForegroundLocationAutoSync(
            authenticated = true,
            permissionGranted = true,
            currentState = "ready",
            presenceStatus = "stale",
            lastAttemptEpochMs = 0L,
            nowEpochMs = 70_000L,
        )

        assertTrue(decision.shouldSync)
        assertEquals("stale_or_unknown_presence", decision.reason)
    }

    @Test
    fun `recent live presence waits for foreground interval`() {
        val decision = evaluateForegroundLocationAutoSync(
            authenticated = true,
            permissionGranted = true,
            currentState = "ready",
            presenceStatus = "live",
            lastAttemptEpochMs = 0L,
            nowEpochMs = 120_000L,
        )

        assertFalse(decision.shouldSync)
        assertEquals("interval_not_elapsed", decision.reason)
    }

    @Test
    fun `sync in flight blocks new auto sync`() {
        val decision = evaluateForegroundLocationAutoSync(
            authenticated = true,
            permissionGranted = true,
            currentState = "syncing",
            presenceStatus = "live",
            lastAttemptEpochMs = 0L,
            nowEpochMs = 400_000L,
        )

        assertFalse(decision.shouldSync)
        assertEquals("sync_in_flight", decision.reason)
    }
}
