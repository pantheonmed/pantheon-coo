import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
} from 'react-native';
import { getApiUrl, setApiUrl, getMe, getToken, logout } from '../services/api';

const BG = '#0f1117';
const ACCENT = '#7c6ff7';
const TEXT = '#e8eaef';
const MUTED = '#8b92a8';

const APP_VERSION = '1.0.0';

export default function SettingsScreen({ onLogout }: { onLogout: () => void }) {
  const [url, setUrl] = useState('');
  const [me, setMe] = useState<any>(null);

  useEffect(() => {
    getApiUrl().then(setUrl);
    (async () => {
      const token = await getToken();
      const m = await getMe(token);
      setMe(m);
    })();
  }, []);

  const saveUrl = async () => {
    const u = url.trim().replace(/\/$/, '');
    if (!u) return;
    await setApiUrl(u);
    Alert.alert('Saved', 'API URL updated.');
  };

  const doLogout = async () => {
    await logout();
    onLogout();
  };

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.pad}>
      <Text style={styles.h}>API URL</Text>
      <Text style={styles.sub}>Default: http://localhost:8002 (use machine IP for device testing)</Text>
      <TextInput
        style={styles.input}
        value={url}
        onChangeText={setUrl}
        placeholder="http://localhost:8002"
        placeholderTextColor={MUTED}
        autoCapitalize="none"
      />
      <TouchableOpacity style={styles.btn} onPress={saveUrl}>
        <Text style={styles.btnText}>Save URL</Text>
      </TouchableOpacity>
      <Text style={[styles.h, { marginTop: 28 }]}>Account</Text>
      <Text style={styles.row}>
        <Text style={styles.muted}>Plan: </Text>
        <Text style={styles.val}>{me?.plan || '—'}</Text>
      </Text>
      <Text style={styles.row}>
        <Text style={styles.muted}>Usage (tasks): </Text>
        <Text style={styles.val}>{me?.usage?.tasks_total ?? '—'}</Text>
      </Text>
      <Text style={styles.row}>
        <Text style={styles.muted}>Email: </Text>
        <Text style={styles.val}>{me?.email || '—'}</Text>
      </Text>
      <Text style={[styles.h, { marginTop: 28 }]}>App</Text>
      <Text style={styles.row}>
        <Text style={styles.muted}>Version: </Text>
        <Text style={styles.val}>{APP_VERSION}</Text>
      </Text>
      <TouchableOpacity style={styles.danger} onPress={doLogout}>
        <Text style={styles.dangerText}>Logout</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: BG },
  pad: { padding: 20, paddingBottom: 48 },
  h: { color: ACCENT, fontSize: 16, fontWeight: '700', marginBottom: 8 },
  sub: { color: MUTED, fontSize: 12, marginBottom: 10 },
  input: {
    backgroundColor: '#1a1d27',
    borderWidth: 1,
    borderColor: '#2a2f3d',
    borderRadius: 10,
    padding: 12,
    color: TEXT,
    marginBottom: 12,
  },
  btn: { backgroundColor: ACCENT, padding: 14, borderRadius: 10, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: '700' },
  row: { marginBottom: 8 },
  muted: { color: MUTED },
  val: { color: TEXT },
  danger: {
    marginTop: 32,
    backgroundColor: '#742a2a',
    padding: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  dangerText: { color: '#feb2b2', fontWeight: '700' },
});
