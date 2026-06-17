import { Redirect, Stack } from 'expo-router';
import { useEffect } from 'react';

import { useAuth } from '@/stores/auth';
import { connectUserSocket, disconnectUserSocket } from '@/stores/realtime';

export default function AppLayout() {
  const user = useAuth((s) => s.user);
  const isReady = useAuth((s) => s.isReady);

  // Keep the user-level WebSocket alive for the whole authenticated session.
  useEffect(() => {
    if (!user) return;
    connectUserSocket();
    return () => disconnectUserSocket();
  }, [user]);

  if (!isReady) return null; // root shows the splash
  if (!user) return <Redirect href="/login" />;

  return (
    <Stack>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="classroom/[id]" options={{ title: 'Classroom' }} />
      <Stack.Screen name="folder/[folderId]" options={{ title: 'Folder' }} />
      <Stack.Screen name="file/[fileId]" options={{ title: 'File' }} />
      <Stack.Screen name="thread/[id]" options={{ title: 'Group chat' }} />
      <Stack.Screen name="folder-quiz/[folderId]" options={{ title: 'Cross-file quiz' }} />
    </Stack>
  );
}
