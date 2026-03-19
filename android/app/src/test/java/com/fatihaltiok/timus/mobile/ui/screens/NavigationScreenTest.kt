package com.fatihaltiok.timus.mobile.ui.screens

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NavigationScreenTest {

    @Test
    fun extractHttpAuthHost_returnsConsoleHost() {
        assertEquals(
            "console.fatih-altiok.com",
            extractHttpAuthHost("https://console.fatih-altiok.com/location/route/mobile_view?reload=1"),
        )
    }

    @Test
    fun extractHttpAuthHost_returnsLocalIpHost() {
        assertEquals(
            "127.0.0.1",
            extractHttpAuthHost("http://127.0.0.1:5000/location/route/mobile_view"),
        )
    }

    @Test
    fun extractHttpAuthHost_returnsNullForInvalidUrl() {
        assertNull(extractHttpAuthHost("not a url"))
    }
}
