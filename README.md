# LeakRepro: an unmounted `secureTextEntry` TextInput is never released on Android

A minimal React Native 0.88.0 app (no dependencies besides `react` and `react-native`). An unmounted `<TextInput secureTextEntry />` that received typed input stays strongly reachable for the life of the process. After the Activity is recreated, the old Activity stays too.

The cause is `TextLayoutManager.tagToSpannableCache`. `ReactEditText.updateCachedSpannable()` copies the text with all spans into it, including `PasswordTransformationMethod.Visible`, which references the field's Editable. The entry is evicted only from `ReactEditText.finalize()`, which can then never run. The full analysis is in the issue: ISSUE_LINK.

## What is here

| File | Purpose |
|---|---|
| `App.tsx` | One `TextInput` (new `key` on every mount), an Unmount/Mount button and a `secureTextEntry` switch |
| `App.measure.tsx` | The same plus an auto-growing `multiline` TextInput that shows its `onLayout` height, used to check that the fix does not change measurement |
| `android/app/build.gradle` | `debuggable true` on the release build type, so a release build (bundled JS, `__DEV__` false, no Metro) can be heap-dumped |
| `android/app/src/main/java/com/leakrepro/MainApplication.kt` | A broadcast receiver for one experiment: it applies the proposed span filter to the spannables already in the cache |
| `repro.sh` | Runs N type → unmount → mount cycles, takes a heap dump after GC and prints what keeps `ReactEditText` and `MainActivity` alive |
| `measure.sh` | Prints the multiline input's height empty and with four lines (needs `App.measure.tsx`) |
| `tools/hprof_paths.py` | Shortest strong paths from GC roots in an Android HPROF; no `hprof-conv` needed |

## Run

`android/app/debug.keystore` is the standard debug keystore from the React Native template, so the release build signs as is.

```sh
npm install
cd android && ./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a && cd ..
adb install -r android/app/build/outputs/apk/release/app-release.apk

./repro.sh secure 5            # the leak
./repro.sh plain 5             # control: plain TextInput
./repro.sh secure 5 recreate   # the old Activity is retained too
```

`repro.sh` checks the app state from the view hierarchy before the cycles and after each of them (the generation goes up by one, the `secureTextEntry` mode stays), and stops with an error if a tap went astray.

Tap positions in `repro.sh` are for a 1080x2400 screen at 420 dpi, the Android Studio "Medium Phone". On another screen set `TOGGLE`, `SECURE` and `INPUT` (see the script header).

## Results (emulator, API 34, arm64)

React Native 0.88.0 unless the row says 0.87.1; every 0.88.0 row gave the same numbers on 0.87.1.

| Run | `ReactEditText` reachable | `MainActivity` reachable |
|---|---|---|
| `secureTextEntry`, 5 cycles | 6 (1 mounted + 5 leaked) | 1 |
| plain `TextInput`, 5 cycles | 1 | 1 |
| `secureTextEntry`, 5 cycles, Activity recreated | 7 | 2 |
| plain `TextInput`, 5 cycles, Activity recreated | 1 | 1 |
| 0.87.1: `secureTextEntry`, 5 cycles, system "Show passwords" off | 1 | 1 |
| 0.87.1: `secureTextEntry`, 5 cycles, then the strip broadcast | 1 | 1 |
| React Native built from source, unpatched | 6 | 1 |
| React Native built from source, unpatched, Activity recreated | 7 | 2 |
| React Native built from source with the fix | 1 | 1 |
| React Native built from source with the fix, Activity recreated | 1 | 1 |
| React Native built from source with the fix, plain `TextInput` | 1 | 1 |

Measurement with `App.measure.tsx` gives the same height with and without the fix: 48 dp empty and 104 dp with four lines.

The strip experiment:

```sh
adb shell am broadcast -a com.leakrepro.STRIP_EDITOR_SPANS -p com.leakrepro
adb logcat -d -s LeakRepro   # cache entries=6, removed={...PasswordTransformationMethod$Visible=5, ...EmojiKeyListener=5}
```

## Build React Native from source with the fix

Apply `fix-0.88.0.patch` with `cd node_modules/react-native && patch -p1 < ../../fix-0.88.0.patch`. Then add this to `android/settings.gradle`, as described in [How to build from source](https://reactnative.dev/contributing/how-to-build-from-source):

```gradle
includeBuild('../node_modules/react-native') {
    dependencySubstitution {
        substitute(module("com.facebook.react:react-android")).using(project(":packages:react-native:ReactAndroid"))
        substitute(module("com.facebook.react:react-native")).using(project(":packages:react-native:ReactAndroid"))
        substitute(module("com.facebook.react:hermes-android")).using(project(":packages:react-native:ReactAndroid:hermes-engine"))
        substitute(module("com.facebook.react:hermes-engine")).using(project(":packages:react-native:ReactAndroid:hermes-engine"))
    }
}
```
