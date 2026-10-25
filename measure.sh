#!/usr/bin/env bash
# Measurement check for the fix. Needs App.measure.tsx as App.tsx: it adds an auto-growing multiline
# TextInput (measured from TextLayoutManager's cached spannable) and prints its onLayout height.
# Prints the height empty and with four lines; compare builds with and without the fix.
set -euo pipefail
PKG=com.leakrepro
a() { adb ${ANDROID_SERIAL:+-s "$ANDROID_SERIAL"} "$@"; }
dump() { a shell "uiautomator dump /data/local/tmp/ui.xml >/dev/null 2>&1; cat /data/local/tmp/ui.xml; rm -f /data/local/tmp/ui.xml"; }
height() { dump | grep -o 'text="multiline height [0-9]*"' | tail -1; }
multiline_xy() { # centre of the node whose hint/text is "multiline"
  dump | tr '>' '\n' | grep 'text="multiline"' | grep -o 'bounds="[^"]*"' | head -1 |
    sed -E 's/bounds="\[([0-9]+),([0-9]+)\]\[([0-9]+),([0-9]+)\]"/\1 \2 \3 \4/' |
    awk '{print int(($1+$3)/2), int(($2+$4)/2)}'
}

a shell am force-stop "$PKG"
a shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
sleep 5
echo "empty:   $(height)"
read -r x y < <(multiline_xy)
a shell input tap "$x" "$y"; sleep 0.8
for w in line1 line2 line3 line4; do
  a shell input text "$w"
  [ "$w" = line4 ] || a shell input keyevent 66   # Enter
  sleep 0.3
done
a shell input keyevent 111; sleep 2
echo "4 lines: $(height)"
