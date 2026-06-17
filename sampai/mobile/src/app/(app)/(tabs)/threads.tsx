import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { groupChatApi } from '@/api/sampai';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Screen } from '@/components/ui/screen';
import { Spinner } from '@/components/ui/spinner';
import { useRealtime } from '@/stores/realtime';

export default function Threads() {
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['threads'],
    queryFn: groupChatApi.threads,
  });
  const unread = useRealtime((s) => s.unread);

  return (
    <Screen edges={['top']}>
      <ScrollView
        contentContainerStyle={{ padding: 24, gap: 12 }}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => void refetch()} />}
      >
        <Text className="text-2xl font-bold text-foreground">Group Chats</Text>

        {isLoading ? (
          <View className="items-center py-8">
            <Spinner size="large" />
          </View>
        ) : (data ?? []).length === 0 ? (
          <EmptyState title="No group chats yet" subtitle="Open a file and invite classmates to start one." />
        ) : (
          (data ?? []).map((t) => {
            const count = t.unread_count + (unread[t.id] ?? 0);
            return (
              <Pressable
                key={t.id}
                onPress={() =>
                  router.push({ pathname: '/thread/[id]', params: { id: String(t.id), name: t.name ?? 'Group chat' } })
                }
              >
                <Card className="gap-1">
                  <View className="flex-row items-center justify-between">
                    <Text className="flex-1 text-base font-semibold text-foreground" numberOfLines={1}>
                      {t.name ?? 'Group chat'}
                    </Text>
                    {count > 0 ? (
                      <View className="rounded-full bg-primary px-2 py-0.5">
                        <Text className="text-xs text-primary-foreground">{count}</Text>
                      </View>
                    ) : null}
                  </View>
                  {t.last_message_preview ? (
                    <Text className="text-muted-foreground" numberOfLines={1}>
                      {t.last_message_preview}
                    </Text>
                  ) : null}
                </Card>
              </Pressable>
            );
          })
        )}
      </ScrollView>
    </Screen>
  );
}
