import React, { useCallback, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, Platform } from 'react-native';
import { useFocusEffect, useRoute } from '@react-navigation/native';
import { getTask, getTaskLogs, getToken } from '../services/api';

const BG = '#0f1117';
const ACCENT = '#7c6ff7';
const TEXT = '#e8eaef';
const MUTED = '#8b92a8';

type Tab = 'logs' | 'plan' | 'eval';

export default function TaskDetailScreen() {
  const route = useRoute<any>();
  const taskId = route.params?.taskId as string;
  const [tab, setTab] = useState<Tab>('logs');
  const [task, setTask] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);

  const load = async () => {
    const token = await getToken();
    const t = await getTask(taskId, token);
    setTask(t);
    const L = await getTaskLogs(taskId, token);
    setLogs(L);
  };

  useFocusEffect(
    useCallback(() => {
      load().catch(() => {});
      const i = setInterval(() => load().catch(() => {}), 4000);
      return () => clearInterval(i);
    }, [taskId])
  );

  if (!task) {
    return (
      <View style={styles.root}>
        <Text style={styles.muted}>Loading…</Text>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      <Text style={styles.goal}>{task.goal || taskId}</Text>
      <View style={styles.badge}>
        <Text style={styles.badgeText}>{task.status}</Text>
      </View>
      <View style={styles.tabs}>
        {(['logs', 'plan', 'eval'] as Tab[]).map((x) => (
          <TouchableOpacity key={x} onPress={() => setTab(x)} style={[styles.tab, tab === x && styles.tabOn]}>
            <Text style={[styles.tabText, tab === x && styles.tabTextOn]}>
              {x === 'eval' ? 'Evaluation' : x.charAt(0).toUpperCase() + x.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
      <ScrollView style={styles.content}>
        {tab === 'logs' &&
          logs.map((L, i) => (
            <Text key={i} style={styles.logLine}>
              <Text style={styles.lv}>{L.level} </Text>
              {L.message}
            </Text>
          ))}
        {tab === 'logs' && logs.length === 0 && <Text style={styles.muted}>No logs yet.</Text>}
        {tab === 'plan' &&
          (task.plan?.steps?.length ? (
            task.plan.steps.map((s: any) => (
              <Text key={s.step_id} style={styles.planStep}>
                #{s.step_id} {s.tool}.{s.action}
                {s.description ? '\n' + s.description : ''}
              </Text>
            ))
          ) : (
            <Text style={styles.muted}>No plan yet.</Text>
          ))}
        {tab === 'eval' && (
          <>
            {task.evaluation_score != null && (
              <Text style={styles.score}>{Number(task.evaluation_score).toFixed(2)}</Text>
            )}
            <Text style={styles.summary}>{task.summary || 'No evaluation yet.'}</Text>
            {task.error ? <Text style={styles.err}>{task.error}</Text> : null}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: BG, padding: 16 },
  goal: { color: TEXT, fontSize: 18, fontWeight: '600', marginBottom: 8 },
  badge: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(124,111,247,0.2)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
    marginBottom: 16,
  },
  badgeText: { color: ACCENT, fontWeight: '700', fontSize: 12 },
  tabs: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  tab: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 8 },
  tabOn: { backgroundColor: 'rgba(124,111,247,0.2)' },
  tabText: { color: MUTED, fontSize: 13 },
  tabTextOn: { color: ACCENT, fontWeight: '600' },
  content: { flex: 1 },
  logLine: { color: TEXT, fontSize: 12, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', marginBottom: 8 },
  lv: { color: MUTED },
  planStep: { color: TEXT, marginBottom: 12, fontSize: 13 },
  score: { fontSize: 36, fontWeight: '700', color: ACCENT, marginBottom: 8 },
  summary: { color: TEXT, fontSize: 14 },
  err: { color: '#f56565', marginTop: 12 },
  muted: { color: MUTED },
});
