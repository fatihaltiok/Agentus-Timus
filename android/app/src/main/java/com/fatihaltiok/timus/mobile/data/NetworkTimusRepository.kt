package com.fatihaltiok.timus.mobile.data

import com.fatihaltiok.timus.mobile.model.ChatMessage
import com.fatihaltiok.timus.mobile.model.ChatReply
import com.fatihaltiok.timus.mobile.model.DeviceLocationSnapshot
import com.fatihaltiok.timus.mobile.model.LocationControlState
import com.fatihaltiok.timus.mobile.model.LocationServerSnapshot
import com.fatihaltiok.timus.mobile.model.VoiceStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

class NetworkTimusRepository : TimusRepository {

    override suspend fun sendChatMessage(
        config: TimusConfig,
        query: String,
        sessionId: String,
    ): Result<ChatReply> = withContext(Dispatchers.IO) {
        runCatching {
            val response = jsonRequest(
                config = config,
                path = "/chat",
                method = "POST",
                body = JSONObject()
                    .put("query", query)
                    .put("session_id", sessionId)
                    .put("input_language", config.inputLanguage)
                    .put("response_language", config.responseLanguage),
            )
            ChatReply(
                agent = response.optString("agent", "executor"),
                reply = response.optString("reply", ""),
                sessionId = response.optString("session_id", sessionId),
            )
        }
    }

    override suspend fun loadChatHistory(config: TimusConfig): Result<List<ChatMessage>> =
        withContext(Dispatchers.IO) {
            runCatching {
                val response = jsonRequest(config = config, path = "/chat/history")
                val history = response.optJSONArray("history") ?: JSONArray()
                buildList {
                    for (index in 0 until history.length()) {
                        val item = history.optJSONObject(index) ?: continue
                        add(
                            ChatMessage(
                                role = item.optString("role", "assistant"),
                                text = item.optString("text", ""),
                                timestamp = item.optString("ts", ""),
                                agent = item.optString("agent").ifBlank { null },
                            ),
                        )
                    }
                }
            }
        }

    override suspend fun fetchVoiceStatus(config: TimusConfig): Result<VoiceStatus> =
        withContext(Dispatchers.IO) {
            runCatching {
                val response = jsonRequest(config = config, path = "/voice/status")
                val voice = response.optJSONObject("voice") ?: JSONObject()
                val voicesArray = voice.optJSONArray("available_voices") ?: JSONArray()
                val voices = buildList {
                    for (index in 0 until voicesArray.length()) {
                        add(voicesArray.optString(index))
                    }
                }
                VoiceStatus(
                    initialized = voice.optBoolean("initialized", false),
                    listening = voice.optBoolean("listening", false),
                    speaking = voice.optBoolean("speaking", false),
                    currentVoice = voice.optString("current_voice", ""),
                    availableVoices = voices,
                )
            }
        }

    override suspend fun transcribeAudio(
        config: TimusConfig,
        fileName: String,
        mimeType: String,
        audioBytes: ByteArray,
    ): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            val boundary = "TimusBoundary-${UUID.randomUUID()}"
            val response = multipartRequest(
                config = config,
                path = "/voice/transcribe",
                boundary = boundary,
                fileName = fileName,
                mimeType = mimeType,
                fileBytes = audioBytes,
            )
            response.optString("text", "")
        }
    }

    override suspend fun synthesizeSpeech(
        config: TimusConfig,
        text: String,
        voice: String?,
    ): Result<ByteArray> = withContext(Dispatchers.IO) {
        runCatching {
            val body = JSONObject().put("text", text)
            if (!voice.isNullOrBlank()) {
                body.put("voice", voice)
            }
            binaryRequest(
                config = config,
                path = "/voice/synthesize",
                method = "POST",
                contentType = "application/json",
                body = body.toString().toByteArray(Charsets.UTF_8),
            )
        }
    }

    override suspend fun fetchLocationStatus(config: TimusConfig): Result<LocationServerSnapshot?> =
        withContext(Dispatchers.IO) {
            runCatching {
                val response = jsonRequest(config = config, path = "/location/status")
                val location = response.optJSONObject("location") ?: return@runCatching null
                parseLocationSnapshot(location)
            }
        }

    override suspend fun fetchLocationControlStatus(config: TimusConfig): Result<LocationControlState> =
        withContext(Dispatchers.IO) {
            runCatching {
                try {
                    val response = jsonRequest(config = config, path = "/location/control")
                    parseLocationControlState(response)
                } catch (error: IllegalStateException) {
                    if (!isHttpNotFound(error)) throw error
                    val legacyStatus = jsonRequest(config = config, path = "/location/status")
                    parseLocationControlState(legacyStatus)
                }
            }
        }

    override suspend fun updateLocationControl(
        config: TimusConfig,
        controls: LocationControlState,
    ): Result<LocationControlState> = withContext(Dispatchers.IO) {
        runCatching {
            try {
                val response = jsonRequest(
                    config = config,
                    path = "/location/control",
                    method = "POST",
                    body = buildLocationControlRequestBody(controls),
                )
                parseLocationControlState(response)
            } catch (error: IllegalStateException) {
                if (isHttpNotFound(error)) {
                    throw IllegalStateException("Server unterstützt Standort-Kontrolle noch nicht.")
                }
                throw error
            }
        }
    }

    override suspend fun resolveLocation(
        config: TimusConfig,
        location: DeviceLocationSnapshot,
    ): Result<LocationServerSnapshot> = withContext(Dispatchers.IO) {
        runCatching {
            val body = JSONObject()
                .put("latitude", location.latitude)
                .put("longitude", location.longitude)
                .put("captured_at", location.capturedAt)
                .put("source", location.source)
            location.accuracyMeters?.let { body.put("accuracy_meters", it.toDouble()) }
            if (!location.deviceId.isNullOrBlank()) body.put("device_id", location.deviceId)
            if (!location.userScope.isNullOrBlank()) body.put("user_scope", location.userScope)
            if (!location.displayName.isNullOrBlank()) body.put("display_name", location.displayName)
            if (!location.locality.isNullOrBlank()) body.put("locality", location.locality)
            if (!location.adminArea.isNullOrBlank()) body.put("admin_area", location.adminArea)
            if (!location.countryName.isNullOrBlank()) body.put("country_name", location.countryName)
            if (!location.countryCode.isNullOrBlank()) body.put("country_code", location.countryCode)

            val response = jsonRequest(
                config = config,
                path = "/location/resolve",
                method = "POST",
                body = body,
            )
            val resolved = response.optJSONObject("location")
                ?: error("Keine Standortdaten vom Server erhalten")
            parseLocationSnapshot(resolved)
        }
    }

    private fun jsonRequest(
        config: TimusConfig,
        path: String,
        method: String = "GET",
        body: JSONObject? = null,
    ): JSONObject {
        val connection = openConnection(config, path, method)
        connection.setRequestProperty("Accept", "application/json")
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { output ->
                output.write(body.toString().toByteArray(Charsets.UTF_8))
            }
        }
        val status = connection.responseCode
        val payload = readAllBytes(
            if (status in 200..299) connection.inputStream else connection.errorStream,
        ).toString(Charsets.UTF_8)
        if (status !in 200..299) {
            throw IllegalStateException("HTTP $status: $payload")
        }
        return JSONObject(payload)
    }

    private fun binaryRequest(
        config: TimusConfig,
        path: String,
        method: String,
        contentType: String,
        body: ByteArray,
    ): ByteArray {
        val connection = openConnection(config, path, method)
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", contentType)
        connection.outputStream.use { output -> output.write(body) }
        val status = connection.responseCode
        val payload = readAllBytes(
            if (status in 200..299) connection.inputStream else connection.errorStream,
        )
        if (status !in 200..299) {
            throw IllegalStateException("HTTP $status: ${payload.toString(Charsets.UTF_8)}")
        }
        return payload
    }

    private fun multipartRequest(
        config: TimusConfig,
        path: String,
        boundary: String,
        fileName: String,
        mimeType: String,
        fileBytes: ByteArray,
    ): JSONObject {
        val connection = openConnection(config, path, "POST")
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")

        DataOutputStream(connection.outputStream).use { output ->
            output.writeBytes("--$boundary\r\n")
            output.writeBytes(
                "Content-Disposition: form-data; name=\"file\"; filename=\"$fileName\"\r\n",
            )
            output.writeBytes("Content-Type: $mimeType\r\n\r\n")
            output.write(fileBytes)
            output.writeBytes("\r\n--$boundary--\r\n")
        }

        val status = connection.responseCode
        val payload = readAllBytes(
            if (status in 200..299) connection.inputStream else connection.errorStream,
        ).toString(Charsets.UTF_8)
        if (status !in 200..299) {
            throw IllegalStateException("HTTP $status: $payload")
        }
        return JSONObject(payload)
    }

    private fun openConnection(
        config: TimusConfig,
        path: String,
        method: String,
    ): HttpURLConnection {
        val url = URL(config.baseUrl.trimEnd('/') + path)
        return (url.openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 20_000
            readTimeout = 60_000
            setRequestProperty("User-Agent", "TimusMobile/0.1")
            config.basicAuthHeaderOrNull()?.let { setRequestProperty("Authorization", it) }
        }
    }

    private fun readAllBytes(stream: java.io.InputStream?): ByteArray {
        if (stream == null) {
            return ByteArray(0)
        }
        BufferedInputStream(stream).use { input ->
            val buffer = ByteArrayOutputStream()
            val data = ByteArray(8 * 1024)
            while (true) {
                val count = input.read(data)
                if (count <= 0) break
                buffer.write(data, 0, count)
            }
            return buffer.toByteArray()
        }
    }

    private fun parseLocationSnapshot(payload: JSONObject): LocationServerSnapshot =
        LocationServerSnapshot(
            latitude = payload.optDouble("latitude"),
            longitude = payload.optDouble("longitude"),
            accuracyMeters = if (payload.has("accuracy_meters") && !payload.isNull("accuracy_meters")) {
                payload.optDouble("accuracy_meters").toFloat()
            } else {
                null
            },
            source = payload.optString("source", "android_fused"),
            capturedAt = payload.optString("captured_at", ""),
            receivedAt = payload.optString("received_at", ""),
            displayName = payload.optString("display_name", ""),
            locality = payload.optString("locality", ""),
            adminArea = payload.optString("admin_area", ""),
            countryName = payload.optString("country_name", ""),
            countryCode = payload.optString("country_code", ""),
            geocodeProvider = payload.optString("geocode_provider", ""),
            mapsUrl = payload.optString("maps_url", ""),
            deviceId = payload.optString("device_id", ""),
            userScope = payload.optString("user_scope", ""),
            presenceStatus = payload.optString("presence_status", "unknown"),
            usableForContext = payload.optBoolean("usable_for_context", false),
            privacyState = payload.optString("privacy_state", "enabled"),
            controlBlockedReason = payload.optString("control_blocked_reason", ""),
        )
}

internal fun parseLocationControlState(payload: JSONObject): LocationControlState {
    val controls = payload.optJSONObject("controls") ?: JSONObject()
    val allowedUserScopesArray = controls.optJSONArray("allowed_user_scopes") ?: JSONArray()
    val allowedUserScopes = buildList {
        for (index in 0 until allowedUserScopesArray.length()) {
            val value = allowedUserScopesArray.optString(index).trim()
            if (value.isNotBlank()) add(value)
        }
    }.ifEmpty { listOf("primary") }
    return buildLocationControlState(
        sharingEnabled = controls.optBoolean("sharing_enabled", true),
        contextEnabled = controls.optBoolean("context_enabled", true),
        backgroundSyncAllowed = controls.optBoolean("background_sync_allowed", true),
        preferredDeviceId = controls.optString("preferred_device_id", ""),
        allowedUserScopes = allowedUserScopes,
        maxDeviceEntries = controls.optInt("max_device_entries", 8).coerceAtLeast(1),
        activeDeviceId = payload.optString("active_device_id", ""),
        activeUserScope = payload.optString("active_user_scope", ""),
        selectionReason = payload.optString("selection_reason", ""),
        deviceCount = payload.optInt("device_count", 0),
    )
}

internal fun buildLocationControlState(
    sharingEnabled: Boolean,
    contextEnabled: Boolean,
    backgroundSyncAllowed: Boolean,
    preferredDeviceId: String,
    allowedUserScopes: List<String>,
    maxDeviceEntries: Int,
    activeDeviceId: String,
    activeUserScope: String,
    selectionReason: String,
    deviceCount: Int,
): LocationControlState {
    val statusMessage = buildString {
        append(
            if (activeDeviceId.isBlank()) {
                "Noch kein aktives Gerät"
            } else {
                "Aktiv: $activeDeviceId"
            },
        )
        if (deviceCount > 0) append(" · Geräte: $deviceCount")
        if (selectionReason.isNotBlank()) append(" · Auswahl: $selectionReason")
        if (preferredDeviceId.isNotBlank()) append(" · Preferred: $preferredDeviceId")
    }
    return LocationControlState(
        state = "ready",
        statusMessage = statusMessage,
        sharingEnabled = sharingEnabled,
        contextEnabled = contextEnabled,
        backgroundSyncAllowed = backgroundSyncAllowed,
        preferredDeviceId = preferredDeviceId,
        allowedUserScopes = allowedUserScopes.ifEmpty { listOf("primary") },
        maxDeviceEntries = maxDeviceEntries.coerceAtLeast(1),
        activeDeviceId = activeDeviceId,
        activeUserScope = activeUserScope,
        selectionReason = selectionReason,
        deviceCount = deviceCount,
        error = null,
    )
}

internal fun buildLocationControlRequestFields(controls: LocationControlState): Map<String, Any> =
    linkedMapOf(
        "sharing_enabled" to controls.sharingEnabled,
        "context_enabled" to controls.contextEnabled,
        "background_sync_allowed" to controls.backgroundSyncAllowed,
        "preferred_device_id" to controls.preferredDeviceId,
        "allowed_user_scopes" to controls.allowedUserScopes,
        "max_device_entries" to controls.maxDeviceEntries,
    )

internal fun buildLocationControlRequestBody(controls: LocationControlState): JSONObject =
    JSONObject().apply {
        buildLocationControlRequestFields(controls).forEach { (key, value) ->
            when (value) {
                is List<*> -> put(key, JSONArray(value))
                else -> put(key, value)
            }
        }
    }

internal fun isHttpNotFound(error: IllegalStateException): Boolean =
    error.message?.contains("HTTP 404", ignoreCase = true) == true
