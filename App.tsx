/**
 * Minimal reproducer: an unmounted <TextInput secureTextEntry /> stays reachable on Android.
 *
 * 1. Tap the input and type a few characters.
 * 2. Tap "Unmount input". Repeat N times ("Mount input" brings a fresh TextInput, new key).
 * 3. Take a heap dump with GC (`adb shell am dumpheap -g <pid> /data/local/tmp/x.hprof`).
 *
 * Expected: one ReactEditText (the mounted one). Actual with secureTextEntry: N + 1 — every
 * unmounted password field is retained by TextLayoutManager's spannable cache. Toggle
 * "secureTextEntry" off to get the control run: the unmounted inputs are collected.
 */
import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

function Button({
  id,
  title,
  onPress,
}: {
  id: string;
  title: string;
  onPress: () => void;
}) {
  return (
    <Pressable testID={id} onPress={onPress} style={styles.button}>
      <Text style={styles.buttonText}>{title}</Text>
    </Pressable>
  );
}

export default function App() {
  const [shown, setShown] = useState(true);
  const [secure, setSecure] = useState(true);
  const [generation, setGeneration] = useState(0);

  return (
    <View style={styles.root}>
      <Text testID="status">{`generation ${generation}, secureTextEntry ${secure}`}</Text>
      <Button
        id="toggle"
        title={shown ? 'Unmount input' : 'Mount input'}
        onPress={() => {
          if (shown) {
            setGeneration(g => g + 1);
          }
          setShown(s => !s);
        }}
      />
      <Button
        id="secure"
        title={`secureTextEntry: ${secure}`}
        onPress={() => setSecure(s => !s)}
      />
      {shown && (
        <TextInput
          key={generation}
          testID="input"
          secureTextEntry={secure}
          placeholder="type here"
          style={styles.input}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    paddingTop: 96,
    paddingHorizontal: 24,
    gap: 16,
    backgroundColor: '#fff',
  },
  button: { padding: 14, borderRadius: 8, backgroundColor: '#2d6cdf' },
  buttonText: { color: '#fff', fontSize: 16, textAlign: 'center' },
  input: {
    borderWidth: 1,
    borderColor: '#999',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
  },
});
