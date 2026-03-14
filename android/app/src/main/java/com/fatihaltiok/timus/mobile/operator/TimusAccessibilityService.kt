package com.fatihaltiok.timus.mobile.operator

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent

class TimusAccessibilityService : AccessibilityService() {

    override fun onServiceConnected() {
        super.onServiceConnected()
        TimusOperatorAccess.markEvent(
            context = this,
            packageName = packageName,
            className = javaClass.simpleName,
            eventType = "service_connected",
        )
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event ?: return
        if (event.eventType !in INTERESTING_EVENTS) {
            return
        }
        TimusOperatorAccess.markEvent(
            context = this,
            packageName = event.packageName,
            className = event.className,
            eventType = eventTypeName(event.eventType),
        )
    }

    override fun onInterrupt() {
        TimusOperatorAccess.markEvent(
            context = this,
            packageName = packageName,
            className = javaClass.simpleName,
            eventType = "interrupt",
        )
    }

    private fun eventTypeName(eventType: Int): String =
        when (eventType) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> "window_state_changed"
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> "window_content_changed"
            AccessibilityEvent.TYPE_VIEW_CLICKED -> "view_clicked"
            AccessibilityEvent.TYPE_VIEW_FOCUSED -> "view_focused"
            AccessibilityEvent.TYPE_VIEW_SCROLLED -> "view_scrolled"
            AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> "view_text_changed"
            else -> "event_$eventType"
        }

    companion object {
        private val INTERESTING_EVENTS = setOf(
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED,
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED,
            AccessibilityEvent.TYPE_VIEW_CLICKED,
            AccessibilityEvent.TYPE_VIEW_FOCUSED,
            AccessibilityEvent.TYPE_VIEW_SCROLLED,
            AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED,
        )
    }
}
