#!/usr/bin/env bash
# Reproduces the leak on a connected emulator/device and prints what keeps ReactEditText and
# MainActivity alive. Needs the release build of this app installed (debuggable, see README).
#
#   ./repro.sh secure|plain [cycles=5] [recreate]
#
#   secure    secureTextEntry on (the default in App.tsx)
#   plain     control run: secureTextEntry switched off first
#   recreate  after the cycles, recreate MainActivity (NEW_TASK|CLEAR_TASK) to check the old one is freed
#
# Each cycle: tap the input, type "abc123", hide the keyboard, Unmount, Mount (a fresh TextInput with a
# new key). Then a heap dump after GC; the dump is deleted after the analysis.
#
# Tap positions are for a 1080x2400 screen at 420 dpi (Android Studio "Medium Phone"); the layout in
# App.tsx is static, so on another screen read them once with `adb shell uiautomator dump` and set
# TOGGLE / SECURE / INPUT as "x,y".
set -euo pipefail
cd "$(dirname "$0")"
PKG=com.leakrepro
MODE=${1:?secure|plain}; N=${2:-5}; EXTRA=${3:-}
case "$MODE" in secure|plain) ;; *) echo "mode must be secure or plain, got '$MODE'" >&2; exit 2 ;; esac
case "$EXTRA" in ''|recreate) ;; *) echo "third argument must be 'recreate' or empty, got '$EXTRA'" >&2; exit 2 ;; esac
TOGGLE=${TOGGLE:-540,410}; SECURE=${SECURE:-540,583}; INPUT=${INPUT:-540,753}
a() { adb ${ANDROID_SERIAL:+-s "$ANDROID_SERIAL"} "$@"; }
tap() { a shell input tap "${1%,*}" "${1#*,}"; }

# The status line, e.g. "generation 0, secureTextEntry true", read from the view hierarchy.
status() {
  a shell uiautomator dump /data/local/tmp/leakrepro-ui.xml >/dev/null 2>&1
  a shell cat /data/local/tmp/leakrepro-ui.xml 2>/dev/null | grep -o 'generation [0-9]*, secureTextEntry [a-z]*'
  a shell rm -f /data/local/tmp/leakrepro-ui.xml
}

a shell am force-stop "$PKG"
a shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
# Wait for the first frame: a tap that lands before it is lost, and the "plain" run would quietly stay secure.
for _ in $(seq 1 30); do [ -n "$(status)" ] && break; sleep 1; done
if [ "$MODE" = plain ]; then tap "$SECURE"; sleep 1; fi
want=$([ "$MODE" = plain ] && echo false || echo true)
case "$(status)" in
  *"secureTextEntry $want") ;;
  *) echo "the app is not in the expected state (secureTextEntry $want): '$(status)'" >&2; exit 1 ;;
esac
for i in $(seq 1 "$N"); do
  tap "$INPUT"; sleep 0.8
  a shell input text abc123; sleep 0.5
  a shell input keyevent 111; sleep 0.5   # hide the keyboard
  tap "$TOGGLE"; sleep 1                  # unmount
  tap "$TOGGLE"; sleep 1                  # mount a fresh TextInput
  # Every cycle must add exactly one generation and keep the mode; a stray tap would skew the count.
  case "$(status)" in
    "generation $i, secureTextEntry $want") ;;
    *) echo "cycle $i went wrong: '$(status)'" >&2; exit 1 ;;
  esac
done
echo "after the cycles: $(status)"
if [ "$EXTRA" = recreate ]; then
  a shell am start -n "$PKG/.MainActivity" -f 0x10008000 >/dev/null
  sleep 4
  echo "after recreating the Activity: $(status)"
fi

DUMP=/data/local/tmp/leakrepro.hprof
a shell am dumpheap -g "$(a shell pidof "$PKG" | tr -d '\r')" "$DUMP" >/dev/null
for _ in $(seq 1 60); do   # wait until the file stops growing
  s1=$(a shell stat -c %s "$DUMP" 2>/dev/null | tr -d '\r'); sleep 1
  s2=$(a shell stat -c %s "$DUMP" 2>/dev/null | tr -d '\r')
  [ -n "$s1" ] && [ "$s1" = "$s2" ] && [ "$s1" -gt 1000 ] && break
done
a pull "$DUMP" leakrepro.hprof >/dev/null
a shell rm -f "$DUMP"
python3 tools/hprof_paths.py leakrepro.hprof com.facebook.react.views.textinput.ReactEditText 4 30
python3 tools/hprof_paths.py leakrepro.hprof com.leakrepro.MainActivity 3 30
rm -f leakrepro.hprof
