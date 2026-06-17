import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail } from '@/api/sampai';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Screen } from '@/components/ui/screen';
import { Spinner } from '@/components/ui/spinner';
import { useClassrooms, useCreateClassroom, useJoinClassroom } from '@/features/classrooms/hooks';
import type { Classroom } from '@/lib/types';
import { useAuth } from '@/stores/auth';

function ClassroomCard({ c }: { c: Classroom }) {
  return (
    <Pressable onPress={() => router.push(`/classroom/${c.id}`)}>
      <Card className="gap-1">
        <Text className="text-base font-semibold text-foreground">{c.name}</Text>
        {c.description ? (
          <Text className="text-muted-foreground" numberOfLines={1}>
            {c.description}
          </Text>
        ) : null}
        <Text className="text-xs text-muted-foreground">
          {c.members.length} member{c.members.length === 1 ? '' : 's'} · code {c.code}
        </Text>
      </Card>
    </Pressable>
  );
}

export default function Dashboard() {
  const user = useAuth((s) => s.user);
  const { data, isLoading, refetch, isRefetching } = useClassrooms();
  const create = useCreateClassroom();
  const join = useJoinClassroom();

  const [showCreate, setShowCreate] = useState(false);
  const [showJoin, setShowJoin] = useState(false);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');

  const created = (data ?? []).filter((c) => c.owner_id === user?.id);
  const joined = (data ?? []).filter((c) => c.owner_id !== user?.id);

  const onCreate = async () => {
    try {
      const c = await create.mutateAsync({ name: name.trim() });
      setShowCreate(false);
      setName('');
      router.push(`/classroom/${c.id}`);
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Could not create classroom'));
    }
  };

  const onJoin = async () => {
    try {
      const c = await join.mutateAsync(code.trim().toUpperCase());
      setShowJoin(false);
      setCode('');
      router.push(`/classroom/${c.id}`);
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Could not join classroom'));
    }
  };

  return (
    <Screen edges={['top']}>
      <ScrollView
        contentContainerStyle={{ padding: 24, gap: 16 }}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => void refetch()} />}
      >
        <Text className="text-2xl font-bold text-foreground">Classrooms</Text>
        <View className="flex-row gap-3">
          <Button label="Create" onPress={() => setShowCreate(true)} className="flex-1" />
          <Button label="Join" variant="secondary" onPress={() => setShowJoin(true)} className="flex-1" />
        </View>

        {isLoading ? (
          <View className="items-center py-8">
            <Spinner size="large" />
          </View>
        ) : (
          <>
            <View className="gap-2">
              <Text className="text-sm font-semibold uppercase text-muted-foreground">Created by you</Text>
              {created.length === 0 ? (
                <Text className="text-muted-foreground">No classrooms yet.</Text>
              ) : (
                created.map((c) => <ClassroomCard key={c.id} c={c} />)
              )}
            </View>
            <View className="gap-2">
              <Text className="text-sm font-semibold uppercase text-muted-foreground">Joined</Text>
              {joined.length === 0 ? (
                <Text className="text-muted-foreground">You haven&apos;t joined any.</Text>
              ) : (
                joined.map((c) => <ClassroomCard key={c.id} c={c} />)
              )}
            </View>
          </>
        )}
      </ScrollView>

      <Dialog visible={showCreate} onClose={() => setShowCreate(false)} title="Create classroom">
        <Input placeholder="Classroom name" value={name} onChangeText={setName} />
        <Button
          label="Create"
          className="mt-3"
          loading={create.isPending}
          disabled={!name.trim() || create.isPending}
          onPress={onCreate}
        />
      </Dialog>

      <Dialog visible={showJoin} onClose={() => setShowJoin(false)} title="Join with code">
        <Input
          placeholder="6-character code"
          autoCapitalize="characters"
          value={code}
          onChangeText={setCode}
          maxLength={6}
        />
        <Button
          label="Join"
          className="mt-3"
          loading={join.isPending}
          disabled={code.trim().length < 4 || join.isPending}
          onPress={onJoin}
        />
      </Dialog>
    </Screen>
  );
}
