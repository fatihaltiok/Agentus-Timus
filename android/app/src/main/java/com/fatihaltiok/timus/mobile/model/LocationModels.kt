package com.fatihaltiok.timus.mobile.model

data class DeviceLocationSnapshot(
    val latitude: Double,
    val longitude: Double,
    val accuracyMeters: Float? = null,
    val source: String = "android_fused",
    val capturedAt: String,
    val deviceId: String? = null,
    val userScope: String? = null,
    val displayName: String? = null,
    val locality: String? = null,
    val adminArea: String? = null,
    val countryName: String? = null,
    val countryCode: String? = null,
)

data class LocationServerSnapshot(
    val latitude: Double,
    val longitude: Double,
    val accuracyMeters: Float? = null,
    val source: String = "android_fused",
    val capturedAt: String,
    val receivedAt: String = "",
    val displayName: String = "",
    val locality: String = "",
    val adminArea: String = "",
    val countryName: String = "",
    val countryCode: String = "",
    val geocodeProvider: String = "",
    val mapsUrl: String = "",
    val deviceId: String = "",
    val userScope: String = "",
    val presenceStatus: String = "unknown",
    val usableForContext: Boolean = false,
    val privacyState: String = "enabled",
    val controlBlockedReason: String = "",
)

data class LocationControlState(
    val state: String = "idle",
    val statusMessage: String = "Standort-Kontrolle noch nicht geladen",
    val sharingEnabled: Boolean = true,
    val contextEnabled: Boolean = true,
    val backgroundSyncAllowed: Boolean = true,
    val preferredDeviceId: String = "",
    val allowedUserScopes: List<String> = listOf("primary"),
    val maxDeviceEntries: Int = 8,
    val activeDeviceId: String = "",
    val activeUserScope: String = "",
    val selectionReason: String = "",
    val deviceCount: Int = 0,
    val error: String? = null,
)

data class LocationUiState(
    val state: String = "idle",
    val permissionState: String = "unknown",
    val statusMessage: String = "Standort noch nicht abgerufen",
    val lastDeviceLocation: DeviceLocationSnapshot? = null,
    val lastResolvedLocation: LocationServerSnapshot? = null,
    val controls: LocationControlState = LocationControlState(),
    val error: String? = null,
)
