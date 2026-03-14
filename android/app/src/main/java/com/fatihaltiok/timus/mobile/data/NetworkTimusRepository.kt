package com.fatihaltiok.timus.mobile.data

import com.fatihaltiok.timus.mobile.model.ChatMessage
import com.fatihaltiok.timus.mobile.model.ChatReply
import com.fatihaltiok.timus.mobile.model.DeviceLocationSnapshot
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
            displayName = payload.optString("display_name", ""),
            locality = payload.optString("locality", ""),
            adminArea = payload.optString("admin_area", ""),
            countryName = payload.optString("country_name", ""),
            countryCode = payload.optString("country_code", ""),
            geocodeProvider = payload.optString("geocode_provider", ""),
            mapsUrl = payload.optString("maps_url", ""),
        )
}
