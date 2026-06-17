import { router, Stack, useLocalSearchParams } from 'expo-router';
import { Folder as FolderIcon, Trash2 } from 'lucide-react-native';
import { useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail } from '@/api/sampai';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Screen } from '@/components/ui/screen';
import { Segmented } from '@/components/ui/segmented';
import { Spinner } from '@/components/ui/spinner';
import { AnnouncementsPanel } from '@/features/announcements/announcements-panel';
import { useClassroom } from '@/features/classrooms/hooks';
import { useCreateFolder, useDeleteFolder, useFolders } from '@/features/folders/hooks';
import { useAuth } from '@/stores/auth';

type Tab = 'files' | 'announcements';

export default function ClassroomDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const classroomId = Number(id);
  const user = useAuth((s) => s.user);
  const { data: classroom } = useClassroom(classroomId);
  const { data: folders, isLoading, refetch, isRefetching } = useFolders(classroomId);
  const createFolder = useCreateFolder(classroomId);
  const deleteFolder = useDeleteFolder(classroomId);

  const isOwner = !!user && classroom?.owner_id === user.id;
  const [tab, setTab] = useState<Tab>('files');
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');

  const onCreate = async () => {
    try {
      await createFolder.mutateAsync(name.trim());
      setShowCreate(false);
      setName('');
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Could not create folder'));
    }
  };

  return (
    <Screen edges={['bottom']}>
      <Stack.Screen options={{ title: classroom?.name ?? 'Classroom' }} />
      <ScrollView
        contentContainerStyle={{ padding: 24, gap: 16 }}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => void refetch()} />}
      >
        {classroom ? (
          <Card className="gap-1">
            {classroom.description ? <Text className="text-foreground">{classroom.description}</Text> : null}
            <Text className="text-xs text-muted-foreground">
              Join code: {classroom.code} · {classroom.members.length} members
            </Text>
          </Card>
        ) : null}

        <Segmented
          value={tab}
          onChange={setTab}
          options={[
            { key: 'files', label: 'Files' },
            { key: 'announcements', label: 'Announcements' },
          ]}
        />

        {tab === 'announcements' ? (
          <AnnouncementsPanel classroomId={classroomId} isOwner={isOwner} userId={user?.id} />
        ) : (
          <>
            <View className="flex-row items-center justify-between">
              <Text className="text-lg font-semibold text-foreground">Folders</Text>
              {isOwner ? (
                <Button label="New folder" variant="secondary" onPress={() => setShowCreate(true)} />
              ) : null}
            </View>

            {isLoading ? (
              <View className="items-center py-6">
                <Spinner />
              </View>
            ) : (folders ?? []).length === 0 ? (
              <Text className="text-muted-foreground">No folders yet.</Text>
            ) : (
              (folders ?? []).map((f) => (
                <Pressable
                  key={f.id}
                  onPress={() =>
                    router.push({
                      pathname: '/folder/[folderId]',
                      params: { folderId: String(f.id), classroomId: String(classroomId), name: f.name },
                    })
                  }
                >
                  <Card className="flex-row items-center gap-3">
                    <FolderIcon color="#1c69e3" size={22} />
                    <View className="flex-1">
                      <Text className="text-base font-semibold text-foreground">{f.name}</Text>
                      <Text className="text-xs text-muted-foreground">
                        {f.files.length} file{f.files.length === 1 ? '' : 's'}
                      </Text>
                    </View>
                    {isOwner ? (
                      <Pressable
                        hitSlop={8}
                        onPress={() =>
                          deleteFolder.mutate(f.id, {
                            onError: (e) => toast.error(apiErrorDetail(e, 'Delete failed')),
                          })
                        }
                      >
                        <Trash2 color="#a20519" size={18} />
                      </Pressable>
                    ) : null}
                  </Card>
                </Pressable>
              ))
            )}
          </>
        )}
      </ScrollView>

      <Dialog visible={showCreate} onClose={() => setShowCreate(false)} title="New folder">
        <Input placeholder="Folder name" value={name} onChangeText={setName} />
        <Button
          label="Create"
          className="mt-3"
          loading={createFolder.isPending}
          disabled={!name.trim() || createFolder.isPending}
          onPress={onCreate}
        />
      </Dialog>
    </Screen>
  );
}
