import { Tabs } from 'expo-router';
import { Bell, Home, MessagesSquare, User } from 'lucide-react-native';

import { useRealtime } from '@/stores/realtime';

export default function TabsLayout() {
  const inviteCount = useRealtime((s) => s.invites.length);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#1c69e3',
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: 'Home', tabBarIcon: ({ color, size }) => <Home color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="threads"
        options={{
          title: 'Threads',
          tabBarIcon: ({ color, size }) => <MessagesSquare color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="notifications"
        options={{
          title: 'Alerts',
          tabBarBadge: inviteCount > 0 ? inviteCount : undefined,
          tabBarIcon: ({ color, size }) => <Bell color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: 'Profile', tabBarIcon: ({ color, size }) => <User color={color} size={size} /> }}
      />
    </Tabs>
  );
}
