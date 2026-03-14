package com.fatihaltiok.timus.mobile.location

import android.annotation.SuppressLint
import android.content.Context
import android.location.Geocoder
import android.location.Location
import android.os.Build
import com.fatihaltiok.timus.mobile.model.DeviceLocationSnapshot
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.time.Instant
import java.util.Locale
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

interface TimusLocationClient {
    suspend fun captureCurrentLocation(): Result<DeviceLocationSnapshot>
}

class AndroidLocationClient(
    context: Context,
) : TimusLocationClient {

    private val appContext = context.applicationContext
    private val fusedClient = LocationServices.getFusedLocationProviderClient(appContext)

    @SuppressLint("MissingPermission")
    override suspend fun captureCurrentLocation(): Result<DeviceLocationSnapshot> =
        withContext(Dispatchers.IO) {
            runCatching {
                val preciseLocation = runCatching {
                    awaitCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY)
                }.getOrNull()

                val location = preciseLocation
                    ?: runCatching { awaitCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY) }.getOrNull()
                    ?: awaitLastKnownLocation()
                    ?: error("Kein Standort verfügbar. Bitte Standortdienste aktivieren.")

                val address = reverseGeocode(location.latitude, location.longitude)
                DeviceLocationSnapshot(
                    latitude = location.latitude,
                    longitude = location.longitude,
                    accuracyMeters = location.accuracy.takeIf { it > 0f },
                    source = if (location.hasAccuracy()) "android_fused" else "android_last_known",
                    capturedAt = Instant.ofEpochMilli(location.time.takeIf { it > 0L } ?: System.currentTimeMillis()).toString(),
                    displayName = address?.getAddressLine(0),
                    locality = address?.locality,
                    adminArea = address?.adminArea,
                    countryName = address?.countryName,
                    countryCode = address?.countryCode,
                )
            }
        }

    @SuppressLint("MissingPermission")
    private suspend fun awaitCurrentLocation(priority: Int): Location? =
        suspendCancellableCoroutine { continuation ->
            val tokenSource = CancellationTokenSource()
            fusedClient.getCurrentLocation(priority, tokenSource.token)
                .addOnSuccessListener { location ->
                    if (continuation.isActive) {
                        continuation.resume(location)
                    }
                }
                .addOnFailureListener { error ->
                    if (continuation.isActive) {
                        continuation.resumeWithException(error)
                    }
                }
            continuation.invokeOnCancellation {
                tokenSource.cancel()
            }
        }

    @SuppressLint("MissingPermission")
    private suspend fun awaitLastKnownLocation(): Location? =
        suspendCancellableCoroutine { continuation ->
            fusedClient.lastLocation
                .addOnSuccessListener { location ->
                    if (continuation.isActive) {
                        continuation.resume(location)
                    }
                }
                .addOnFailureListener { error ->
                    if (continuation.isActive) {
                        continuation.resumeWithException(error)
                    }
                }
        }

    private fun reverseGeocode(latitude: Double, longitude: Double): android.location.Address? {
        if (!Geocoder.isPresent()) {
            return null
        }
        val geocoder = Geocoder(appContext, Locale.getDefault())
        return runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                var result: android.location.Address? = null
                val lock = java.lang.Object()
                var completed = false
                geocoder.getFromLocation(latitude, longitude, 1) { addresses ->
                    synchronized(lock) {
                        result = addresses.firstOrNull()
                        completed = true
                        lock.notifyAll()
                    }
                }
                synchronized(lock) {
                    if (!completed) {
                        lock.wait(2_500L)
                    }
                }
                result
            } else {
                @Suppress("DEPRECATION")
                geocoder.getFromLocation(latitude, longitude, 1)?.firstOrNull()
            }
        }.getOrNull()
    }
}
