package com.fatihaltiok.timus.mobile.model

data class DeviceLocationSnapshot(
    val latitude: Double,
    val longitude: Double,
    val accuracyMeters: Float? = null,
    val source: String = "android_fused",
    val capturedAt: String,
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
    val displayName: String = "",
    val locality: String = "",
    val adminArea: String = "",
    val countryName: String = "",
    val countryCode: String = "",
    val geocodeProvider: String = "",
    val mapsUrl: String = "",
)

data class LocationUiState(
    val state: String = "idle",
    val permissionState: String = "unknown",
    val statusMessage: String = "Standort noch nicht abgerufen",
    val lastDeviceLocation: DeviceLocationSnapshot? = null,
    val lastResolvedLocation: LocationServerSnapshot? = null,
    val error: String? = null,
)
