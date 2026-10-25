package com.leakrepro

import android.app.Application
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.text.Spannable
import android.text.style.CharacterStyle
import android.text.style.ParagraphStyle
import android.util.Log
import com.facebook.react.PackageList
import com.facebook.react.ReactApplication
import com.facebook.react.ReactHost
import com.facebook.react.ReactNativeApplicationEntryPoint.loadReactNative
import com.facebook.react.defaults.DefaultReactHost.getDefaultReactHost

class MainApplication : Application(), ReactApplication {

  override val reactHost: ReactHost by lazy {
    getDefaultReactHost(
      context = applicationContext,
      packageList =
        PackageList(this).packages.apply {
          // Packages that cannot be autolinked yet can be added manually here, for example:
          // add(MyReactNativePackage())
        },
    )
  }

  override fun onCreate() {
    super.onCreate()
    loadReactNative(this)
    registerStripReceiver()
  }

  /**
   * Reproducer only. `adb shell am broadcast -a com.leakrepro.STRIP_EDITOR_SPANS -p com.leakrepro`
   * applies the proposed fix's filter to what is already in TextLayoutManager's spannable cache: keep
   * style spans (CharacterStyle, ParagraphStyle) and React Native's own spans, drop the rest (editor
   * bookkeeping such as PasswordTransformationMethod's Visible). If the unmounted ReactEditTexts become
   * collectable after this, that span was the only thing keeping them.
   */
  private fun registerStripReceiver() {
    val receiver =
      object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
          val field =
            Class.forName("com.facebook.react.views.text.TextLayoutManager")
              .getDeclaredField("tagToSpannableCache")
              .apply { isAccessible = true }
          @Suppress("UNCHECKED_CAST") val cache = field.get(null) as Map<Int, Spannable>
          val removed = mutableMapOf<String, Int>()
          for (spannable in cache.values) {
            for (span in spannable.getSpans(0, spannable.length, Any::class.java)) {
              val reactSpan = span.javaClass.name.startsWith("com.facebook.react.")
              if (span !is CharacterStyle && span !is ParagraphStyle && !reactSpan) {
                spannable.removeSpan(span)
                removed.merge(span.javaClass.name, 1, Int::plus)
              }
            }
          }
          Log.w("LeakRepro", "cache entries=${cache.size}, removed=$removed")
        }
      }
    val filter = IntentFilter("com.leakrepro.STRIP_EDITOR_SPANS")
    if (Build.VERSION.SDK_INT >= 33) {
      registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED)
    } else {
      @Suppress("UnspecifiedRegisterReceiverFlag") registerReceiver(receiver, filter)
    }
  }
}
