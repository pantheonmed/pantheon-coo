import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, Alert } from 'react-native';
import { Audio } from 'expo-av';
import { getToken, transcribeAndExecute } from '../services/api';
import { useNavigation } from '@react-navigation/native';

const BG = '#0f1117';
const ACCENT = '#7c6ff7';
const TEXT = '#e8eaef';
const MUTED = '#8b92a8';

export default function VoiceScreen() {
  const navigation = useNavigation<any>();
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [busy, setBusy] = useState(false);

  const start = async () => {
    try {
      await Audio.requestPermissionsAsync();
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording: rec } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      setRecording(rec);
    } catch (e: any) {
      Alert.alert('Mic error', e?.message || 'Could not start recording');
    }
  };

  const stopAndSend = async () => {
    if (!recording) return;
    setBusy(true);
    try {
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      setRecording(null);
      if (!uri) throw new Error('No recording file');
      const token = await getToken();
      const out = await transcribeAndExecute(uri, token);
      if (out.task_id) navigation.navigate('TaskDetail', { taskId: out.task_id });
      else Alert.alert('Transcribed', out.text || 'Done');
    } catch (e: any) {
      Alert.alert('Error', e?.message || 'Transcription failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.root}>
      <Text style={styles.title}>Voice command</Text>
      <Text style={styles.sub}>Record, then we transcribe via POST /voice/transcribe and run the task.</Text>
      {!recording ? (
        <TouchableOpacity style={styles.mic} onPress={start} disabled={busy}>
          <Text style={styles.micText}>● Record</Text>
        </TouchableOpacity>
      ) : (
        <TouchableOpacity style={styles.stop} onPress={stopAndSend} disabled={busy}>
          {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.micText}>Stop &amp; submit</Text>}
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: BG, padding: 24, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 22, fontWeight: '700', color: TEXT, marginBottom: 8 },
  sub: { color: MUTED, textAlign: 'center', marginBottom: 32, paddingHorizontal: 16 },
  mic: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: ACCENT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stop: {
    width: 160,
    height: 56,
    borderRadius: 12,
    backgroundColor: '#742a2a',
    alignItems: 'center',
    justifyContent: 'center',
  },
  micText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
