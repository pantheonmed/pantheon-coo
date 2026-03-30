import React, { useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { ActivityIndicator, View, StyleSheet } from 'react-native';
import LoginScreen from './screens/LoginScreen';
import DashboardScreen from './screens/DashboardScreen';
import TaskDetailScreen from './screens/TaskDetailScreen';
import VoiceScreen from './screens/VoiceScreen';
import SettingsScreen from './screens/SettingsScreen';
import { getToken } from './services/api';

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

function HomeStack() {
  return (
    <Stack.Navigator screenOptions={{ headerStyle: { backgroundColor: '#1a1d27' }, headerTintColor: '#e8eaef' }}>
      <Stack.Screen name="DashboardHome" options={{ title: 'Home' }}>
        {() => <DashboardScreen historyOnly={false} />}
      </Stack.Screen>
      <Stack.Screen name="TaskDetail" component={TaskDetailScreen} options={{ title: 'Task' }} />
    </Stack.Navigator>
  );
}

function HistoryStack() {
  return (
    <Stack.Navigator screenOptions={{ headerStyle: { backgroundColor: '#1a1d27' }, headerTintColor: '#e8eaef' }}>
      <Stack.Screen name="DashboardHistory" options={{ title: 'History' }}>
        {() => <DashboardScreen historyOnly />}
      </Stack.Screen>
      <Stack.Screen name="TaskDetail" component={TaskDetailScreen} options={{ title: 'Task' }} />
    </Stack.Navigator>
  );
}

function MainTabs({ onLogout }: { onLogout: () => void }) {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: '#1a1d27', borderTopColor: '#2a2f3d' },
        tabBarActiveTintColor: '#7c6ff7',
        tabBarInactiveTintColor: '#8b92a8',
      }}
    >
      <Tab.Screen name="Home" component={HomeStack} options={{ title: 'Home' }} />
      <Tab.Screen name="History" component={HistoryStack} />
      <Tab.Screen name="Voice" component={VoiceScreen} />
      <Tab.Screen name="Settings">
        {() => <SettingsScreen onLogout={onLogout} />}
      </Tab.Screen>
    </Tab.Navigator>
  );
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    (async () => {
      const t = await getToken();
      setLoggedIn(!!t);
      setReady(true);
    })();
  }, []);

  if (!ready) {
    return (
      <View style={styles.splash}>
        <ActivityIndicator size="large" color="#7c6ff7" />
      </View>
    );
  }

  return (
    <NavigationContainer>
      <StatusBar style="light" />
      {!loggedIn ? (
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen name="Login">
            {() => <LoginScreen onLoggedIn={() => setLoggedIn(true)} />}
          </Stack.Screen>
        </Stack.Navigator>
      ) : (
        <MainTabs onLogout={() => setLoggedIn(false)} />
      )}
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  splash: { flex: 1, backgroundColor: '#0f1117', alignItems: 'center', justifyContent: 'center' },
});
