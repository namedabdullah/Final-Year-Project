import '@/global.css';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Toaster } from 'sonner-native';

import { ErrorBoundary } from '@/components/error-boundary';
import { authEvents } from '@/lib/auth-events';
import { useAuth } from '@/stores/auth';
import { hydrateTheme } from '@/stores/theme';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

function RootNavigator() {
  const isReady = useAuth((s) => s.isReady);
  const bootstrap = useAuth((s) => s.bootstrap);
  const logout = useAuth((s) => s.logout);

  useEffect(() => {
    void hydrateTheme();
    void bootstrap();
    // axios 401 interceptor -> global sign-out
    const off = authEvents.onLogout(() => {
      void logout();
    });
    return off;
  }, [bootstrap, logout]);

  if (!isReady) {
    return (
      <View className="flex-1 items-center justify-center bg-background">
        <ActivityIndicator size="large" color="#1c69e3" />
      </View>
    );
  }

  return <Stack screenOptions={{ headerShown: false }} />;
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <StatusBar style="auto" />
          <ErrorBoundary>
            <RootNavigator />
          </ErrorBoundary>
          <Toaster />
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
