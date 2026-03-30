import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { login } from '../services/api';

const BG = '#0f1117';
const ACCENT = '#7c6ff7';
const TEXT = '#e8eaef';
const MUTED = '#8b92a8';

export default function LoginScreen({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setErr('');
    setLoading(true);
    try {
      await login(email.trim(), password);
      onLoggedIn();
    } catch (e: any) {
      setErr(e?.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <Text style={styles.logo}>
        Pantheon <Text style={styles.logoAccent}>COO OS</Text>
      </Text>
      <Text style={styles.sub}>Sign in to continue</Text>
      <TextInput
        style={styles.input}
        placeholder="Email"
        placeholderTextColor={MUTED}
        autoCapitalize="none"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <TextInput
        style={styles.input}
        placeholder="Password"
        placeholderTextColor={MUTED}
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />
      {err ? <Text style={styles.err}>{err}</Text> : null}
      <TouchableOpacity style={styles.btn} onPress={submit} disabled={loading}>
        {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Login</Text>}
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: BG, padding: 24, justifyContent: 'center' },
  logo: { fontSize: 24, fontWeight: '700', color: TEXT, marginBottom: 8 },
  logoAccent: { color: ACCENT },
  sub: { color: MUTED, marginBottom: 24 },
  input: {
    backgroundColor: '#1a1d27',
    borderWidth: 1,
    borderColor: '#2a2f3d',
    borderRadius: 10,
    padding: 14,
    color: TEXT,
    marginBottom: 12,
  },
  err: { color: '#f56565', marginBottom: 12 },
  btn: {
    backgroundColor: ACCENT,
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 8,
  },
  btnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
