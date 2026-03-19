package com.fatihaltiok.timus.mobile.ui.screens

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewDatabase
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.unit.dp
import com.fatihaltiok.timus.mobile.data.TimusConfig
import com.fatihaltiok.timus.mobile.model.LocationUiState
import com.fatihaltiok.timus.mobile.ui.components.TimusCard
import com.fatihaltiok.timus.mobile.ui.theme.Night0
import com.fatihaltiok.timus.mobile.ui.theme.PanelStrong
import com.fatihaltiok.timus.mobile.ui.theme.TimusPrimary
import java.net.URI

@Composable
fun NavigationScreen(
    config: TimusConfig,
    locationState: LocationUiState,
) {
    var reloadNonce by remember { mutableIntStateOf(0) }
    var pageState by remember { mutableStateOf("laedt") }
    var pageError by remember { mutableStateOf<String?>(null) }
    val mobileRouteUrl = remember(config.baseUrl, reloadNonce) {
        buildMobileRouteUrl(
            baseUrl = config.baseUrl,
            reloadNonce = reloadNonce,
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TimusCard(
            title = "Navigation",
            subtitle = buildNavigationSubtitle(locationState, pageState, pageError),
            status = if (pageError.isNullOrBlank()) locationState.state else "error",
            trailing = {
                Button(
                    onClick = { reloadNonce += 1 },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = TimusPrimary,
                        contentColor = Night0,
                        disabledContainerColor = PanelStrong,
                    ),
                ) {
                    Text("Neu laden")
                }
            },
        )

        RouteMapWebView(
            url = mobileRouteUrl,
            username = config.username,
            password = config.password,
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            onLoadingState = { state, error ->
                pageState = state
                pageError = error
            },
        )
    }
}

private fun buildNavigationSubtitle(
    locationState: LocationUiState,
    pageState: String,
    pageError: String?,
): String {
    val locationSummary = locationState.lastResolvedLocation?.let { resolved ->
        val label = resolved.displayName.ifBlank {
            listOf(resolved.locality, resolved.adminArea, resolved.countryName)
                .filter { it.isNotBlank() }
                .joinToString(", ")
        }.ifBlank { "${resolved.latitude}, ${resolved.longitude}" }
        "$label · ${resolved.presenceStatus.ifBlank { "unknown" }}"
    } ?: "Noch kein Standort synchronisiert"
    val pageSummary = if (pageError.isNullOrBlank()) {
        "Route-View $pageState"
    } else {
        "WebView-Fehler: $pageError"
    }
    return "$locationSummary\n$pageSummary"
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun RouteMapWebView(
    url: String,
    username: String,
    password: String,
    modifier: Modifier = Modifier,
    onLoadingState: (state: String, error: String?) -> Unit,
) {
    AndroidView(
        modifier = modifier,
        factory = { context ->
            WebView(context).apply {
                seedWebViewHttpAuth(context, url, username, password)
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.builtInZoomControls = true
                settings.displayZoomControls = false
                settings.useWideViewPort = true
                settings.loadWithOverviewMode = true
                settings.setSupportZoom(true)
                settings.cacheMode = WebSettings.LOAD_NO_CACHE
                overScrollMode = WebView.OVER_SCROLL_NEVER
                webChromeClient = WebChromeClient()
                webViewClient = object : WebViewClient() {
                    override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                        onLoadingState("laedt", null)
                    }

                    override fun onPageFinished(view: WebView?, url: String?) {
                        onLoadingState("bereit", null)
                    }

                    override fun onReceivedError(
                        view: WebView?,
                        request: WebResourceRequest?,
                        error: WebResourceError?,
                    ) {
                        if (request?.isForMainFrame == true) {
                            onLoadingState("fehler", error?.description?.toString())
                        }
                    }

                    override fun onReceivedHttpAuthRequest(
                        view: WebView?,
                        handler: android.webkit.HttpAuthHandler?,
                        host: String?,
                        realm: String?,
                    ) {
                        if (username.isNotBlank() && password.isNotBlank()) {
                            WebViewDatabase.getInstance(context).setHttpAuthUsernamePassword(
                                host.orEmpty(),
                                realm.orEmpty(),
                                username,
                                password,
                            )
                            handler?.proceed(username, password)
                        } else {
                            onLoadingState(
                                "auth",
                                "Navigation erfordert Zugangsdaten fuer ${host.orEmpty()}",
                            )
                            handler?.cancel()
                        }
                    }
                }
                loadRoute(url = url)
            }
        },
        update = { webView ->
            if (webView.url != url) {
                seedWebViewHttpAuth(webView.context, url, username, password)
                webView.loadRoute(url = url)
            }
        },
    )
}

private fun buildMobileRouteUrl(
    baseUrl: String,
    reloadNonce: Int,
): String {
    val normalizedBaseUrl = baseUrl.trim().trimEnd('/')
    if (normalizedBaseUrl.isBlank()) return "about:blank"
    return "$normalizedBaseUrl/location/route/mobile_view?reload=$reloadNonce&client=android"
}

internal fun extractHttpAuthHost(url: String): String? {
    val normalized = url.trim()
    if (normalized.isBlank()) return null
    return try {
        URI(normalized).host?.takeIf { it.isNotBlank() }
    } catch (_: Exception) {
        null
    }
}

private fun seedWebViewHttpAuth(
    context: android.content.Context,
    url: String,
    username: String,
    password: String,
) {
    if (username.isBlank() || password.isBlank()) return
    val host = extractHttpAuthHost(url) ?: return
    WebViewDatabase.getInstance(context).setHttpAuthUsernamePassword(
        host,
        "restricted",
        username,
        password,
    )
}

private fun WebView.loadRoute(
    url: String,
) {
    loadUrl(url)
}
