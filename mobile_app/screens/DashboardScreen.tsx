import React, { useCallback, useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  FlatList,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { execute, getToken, listTasks } from '../services/api';

const BG = '#0f1117';
const ACCENT = '#7c6ff7';
const TEXT = '#e8eaef';
const MUTED = '#8b92a8';

export default function DashboardScreen({ historyOnly = false }: { historyOnly?: boolean }) {
  const navigation = useNavigation<any>();
  const [cmd, setCmd] = useState('');
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    const token = await getToken();
    const data = await listTasks(token);
    setTasks(data.tasks || []);
  };

  useFocusEffect(
    useCallback(() => {
      let t: ReturnType<typeof setInterval>;
      load().catch(() => setTasks([]));
      t = setInterval(() => load().catch(() => {}), 5000);
      return () => clearInterval(t);
    }, [])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  };

  const run = async (dry: boolean) => {
    const c = cmd.trim();
    if (c.length < 3) return;
    setLoading(true);
    try {
      const token = await getToken();
      const res = await execute(c, dry, token);
      setCmd('');
      navigation.navigate('TaskDetail', { taskId: res.task_id });
      await load();
    } catch (e: any) {
      /* handled in UI optionally */
    } finally {
      setLoading(false);
    }
  };

  const badge = (s: string) => {
    const st = (s || '').toLowerCase();
    let bg = '#374151';
    if (st === 'done') bg = 'rgba(61,214,140,0.25)';
    if (st === 'failed') bg = 'rgba(245,101,101,0.25)';
    return bg;
  };

  return (
    <View style={styles.root}>
      {!historyOnly && (
        <>
          <Text style={styles.label}>Command</Text>
          <TextInput
            style={styles.input}
            placeholder="Tell COO what to do..."
            placeholderTextColor={MUTED}
            multiline
            value={cmd}
            onChangeText={setCmd}
          />
          <View style={styles.row}>
            <TouchableOpacity style={styles.btn} onPress={() => run(false)} disabled={loading}>
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Execute</Text>}
            </TouchableOpacity>
            <TouchableOpacity style={styles.btnGhost} onPress={() => run(true)} disabled={loading}>
              <Text style={styles.btnGhostText}>Dry run</Text>
            </TouchableOpacity>
          </View>
        </>
      )}
      <Text style={styles.section}>{historyOnly ? 'All tasks' : 'Recent tasks'}</Text>
      <FlatList
        data={tasks}
        keyExtractor={(item) => item.task_id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={ACCENT} />}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={styles.taskRow}
            onPress={() => navigation.navigate('TaskDetail', { taskId: item.task_id })}
          >
            <Text style={styles.goal} numberOfLines={2}>
              {item.goal || item.task_id}
            </Text>
            <View style={[styles.badge, { backgroundColor: badge(item.status) }]}>
              <Text style={styles.badgeText}>{item.status}</Text>
            </View>
          </TouchableOpacity>
        )}
        ListEmptyComponent={<Text style={styles.empty}>No tasks yet.</Text>}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: BG, padding: 16 },
  label: { color: MUTED, fontSize: 11, textTransform: 'uppercase', marginBottom: 6 },
  input: {
    minHeight: 100,
    backgroundColor: '#1a1d27',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#2a2f3d',
    color: TEXT,
    padding: 12,
    textAlignVertical: 'top',
    marginBottom: 12,
  },
  row: { flexDirection: 'row', gap: 10, marginBottom: 20 },
  btn: {
    flex: 1,
    backgroundColor: ACCENT,
    padding: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  btnText: { color: '#fff', fontWeight: '700' },
  btnGhost: {
    paddingHorizontal: 16,
    justifyContent: 'center',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#2a2f3d',
  },
  btnGhostText: { color: TEXT },
  section: { color: MUTED, fontSize: 12, marginBottom: 8, textTransform: 'uppercase' },
  taskRow: {
    padding: 14,
    backgroundColor: '#1a1d27',
    borderRadius: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#2a2f3d',
  },
  goal: { color: TEXT, marginBottom: 8 },
  badge: { alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  badgeText: { fontSize: 11, fontWeight: '600', color: TEXT },
  empty: { color: MUTED, textAlign: 'center', marginTop: 24 },
});
