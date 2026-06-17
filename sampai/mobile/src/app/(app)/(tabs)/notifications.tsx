import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ScrollView, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail, groupChatApi } from '@/api/sampai';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Screen } from '@/components/ui/screen';
import { useRealtime } from '@/stores/realtime';

export default function Notifications() {
  const qc = useQueryClient();
  const invites = useRealtime((s) => s.invites);
  const announcements = useRealtime((s) => s.announcements);
  const removeInvite = useRealtime((s) => s.removeInvite);

  const accept = useMutation({
    mutationFn: (inviteId: number) => groupChatApi.accept(inviteId),
    onSuccess: (_d, inviteId) => {
      removeInvite(inviteId);
      void qc.invalidateQueries({ queryKey: ['threads'] });
      toast.success('Joined group chat');
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not accept')),
  });

  const reject = useMutation({
    mutationFn: (inviteId: number) => groupChatApi.reject(inviteId),
    onSuccess: (_d, inviteId) => removeInvite(inviteId),
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not decline')),
  });

  return (
    <Screen edges={['top']}>
      <ScrollView contentContainerStyle={{ padding: 24, gap: 12 }}>
        <Text className="text-2xl font-bold text-foreground">Notifications</Text>

        <Text className="text-sm font-semibold uppercase text-muted-foreground">Invites</Text>
        {invites.length === 0 ? (
          <Text className="text-muted-foreground">No pending invites.</Text>
        ) : (
          invites.map((inv) => (
            <Card key={inv.id} className="gap-2">
              <Text className="text-foreground">
                <Text className="font-semibold">{inv.inviter.username}</Text> invited you to a group chat
              </Text>
              <View className="flex-row gap-2">
                <Button
                  label="Accept"
                  className="flex-1"
                  loading={accept.isPending}
                  onPress={() => accept.mutate(inv.id)}
                />
                <Button
                  label="Decline"
                  variant="secondary"
                  className="flex-1"
                  onPress={() => reject.mutate(inv.id)}
                />
              </View>
            </Card>
          ))
        )}

        {announcements.length > 0 ? (
          <>
            <Text className="mt-2 text-sm font-semibold uppercase text-muted-foreground">Recent</Text>
            {announcements.map((a, i) => (
              <Card key={`${a.announcementId}-${i}`}>
                <Text className="text-muted-foreground">
                  <Text className="font-semibold text-foreground">{a.by}</Text>{' '}
                  {a.kind === 'comment' ? 'commented on an announcement' : 'posted an announcement'}
                </Text>
              </Card>
            ))}
          </>
        ) : null}
      </ScrollView>
    </Screen>
  );
}
