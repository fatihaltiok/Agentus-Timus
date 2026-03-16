package com.fatihaltiok.timus.mobile.location

import com.fatihaltiok.timus.mobile.data.buildLocationControlRequestFields
import com.fatihaltiok.timus.mobile.data.buildLocationControlState
import com.fatihaltiok.timus.mobile.model.LocationControlState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocationControlParserTest {

    @Test
    fun buildLocationControlState_reads_flags_and_metadata() {
        val result = buildLocationControlState(
            sharingEnabled = false,
            contextEnabled = true,
            backgroundSyncAllowed = false,
            preferredDeviceId = "pixel8",
            allowedUserScopes = listOf("primary", "travel"),
            maxDeviceEntries = 6,
            activeDeviceId = "pixel8",
            activeUserScope = "primary",
            selectionReason = "preferred_device",
            deviceCount = 2,
        )

        assertEquals("ready", result.state)
        assertFalse(result.sharingEnabled)
        assertTrue(result.contextEnabled)
        assertFalse(result.backgroundSyncAllowed)
        assertEquals("pixel8", result.preferredDeviceId)
        assertEquals(listOf("primary", "travel"), result.allowedUserScopes)
        assertEquals(6, result.maxDeviceEntries)
        assertEquals("pixel8", result.activeDeviceId)
        assertEquals("primary", result.activeUserScope)
        assertEquals("preferred_device", result.selectionReason)
        assertEquals(2, result.deviceCount)
    }

    @Test
    fun buildLocationControlRequestFields_serializes_expected_fields() {
        val fields = buildLocationControlRequestFields(
            LocationControlState(
                sharingEnabled = true,
                contextEnabled = false,
                backgroundSyncAllowed = true,
                preferredDeviceId = "tablet7",
                allowedUserScopes = listOf("primary", "travel"),
                maxDeviceEntries = 9,
            ),
        )

        assertTrue(fields["sharing_enabled"] as Boolean)
        assertFalse(fields["context_enabled"] as Boolean)
        assertTrue(fields["background_sync_allowed"] as Boolean)
        assertEquals("tablet7", fields["preferred_device_id"])
        assertEquals(listOf("primary", "travel"), fields["allowed_user_scopes"])
        assertEquals(9, fields["max_device_entries"])
    }
}
