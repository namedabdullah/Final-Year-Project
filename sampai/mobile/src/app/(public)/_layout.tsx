import { Redirect, Stack } from 'expo-router';

import { useAuth } from '@/stores/auth';

export default function PublicLayout() {
  const user = useAuth((s) => s.user);
  const isReady = useAuth((s) => s.isReady);

  if (!isReady) return null; // root shows the splash
  if (user) return <Redirect href="/" />;

  return <Stack screenOptions={{ headerShown: false }} />;
}
