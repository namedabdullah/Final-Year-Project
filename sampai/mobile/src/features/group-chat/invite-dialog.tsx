import { useMutation, useQuery } from '@tanstack/react-query';
import { Check } from 'lucide-react-native';
import { useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail, groupChatApi } from '@/api/sampai';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';

export function InviteDialog({
  fileId,
  visible,
  onClose,
}: {
  fileId: number;
  visible: boolean;
  onClose: () => void;
}) {
  const eligible = useQuery({
    queryKey: ['eligible', fileId],
    queryFn: () => groupChatApi.eligible(fileId),
    enabled: visible,
  });
  const [sel, setSel] = useState<number[]>([]);

  const invite = useMutation({
    mutationFn: () => groupChatApi.invite(fileId, sel),
    onSuccess: () => {
      toast.success('Invites sent');
      setSel([]);
      onClose();
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not send invites')),
  });

  const toggle = (uid: number) =>
    setSel((s) => (s.includes(uid) ? s.filter((x) => x !== uid) : [...s, uid]));

  return (
    <Dialog visible={visible} onClose={onClose} title="Invite to group chat">
      {eligible.isLoading ? (
        <Spinner />
      ) : (eligible.data ?? []).length === 0 ? (
        <Text className="text-muted-foreground">No classmates available to invite.</Text>
      ) : (
        <ScrollView style={{ maxHeight: 280 }}>
          {(eligible.data ?? []).map((u) => {
            const on = sel.includes(u.id);
            return (
              <Pressable
                key={u.id}
                onPress={() => toggle(u.id)}
                className="flex-row items-center justify-between py-2"
              >
                <Text className="text-foreground">{u.username}</Text>
                <View
                  className={cn(
                    'h-5 w-5 items-center justify-center rounded border',
                    on ? 'border-primary bg-primary' : 'border-border',
                  )}
                >
                  {on ? <Check size={14} color="#f9fcff" /> : null}
                </View>
              </Pressable>
            );
          })}
        </ScrollView>
      )}
      <Button
        label={`Invite${sel.length ? ` (${sel.length})` : ''}`}
        className="mt-3"
        loading={invite.isPending}
        disabled={sel.length === 0 || invite.isPending}
        onPress={() => invite.mutate()}
      />
    </Dialog>
  );
}
