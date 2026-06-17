import { router, Stack, useLocalSearchParams } from 'expo-router';
import { Download, MessageSquarePlus, Trash2 } from 'lucide-react-native';
import { useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail, fileApi } from '@/api/sampai';
import { FileStatusBadge } from '@/components/file-status-badge';
import { Screen } from '@/components/ui/screen';
import { Segmented } from '@/components/ui/segmented';
import { Spinner } from '@/components/ui/spinner';
import { ChatPanel } from '@/features/chat/chat-panel';
import { useClassroom } from '@/features/classrooms/hooks';
import { FlashcardsPanel } from '@/features/flashcards/flashcards-panel';
import { InviteDialog } from '@/features/group-chat/invite-dialog';
import { MindmapPanel } from '@/features/mindmap/mindmap-panel';
import { QuizPanel } from '@/features/quiz/quiz-panel';
import { useDeleteFile, useFile, useFileStatus } from '@/features/files/hooks';
import { useAuth } from '@/stores/auth';

type Tab = 'chat' | 'quiz' | 'flashcards' | 'mindmap';

function Locked({ text }: { text: string }) {
  return (
    <View className="flex-1 items-center justify-center p-6">
      <Text className="text-center text-muted-foreground">{text}</Text>
    </View>
  );
}

export default function FileDetail() {
  const { fileId, folderId, classroomId } = useLocalSearchParams<{
    fileId: string;
    folderId?: string;
    classroomId?: string;
  }>();
  const id = Number(fileId);
  const fid = Number(folderId);
  const cid = Number(classroomId);

  const user = useAuth((s) => s.user);
  const { data: file, isLoading } = useFile(id);
  const { data: status } = useFileStatus(id);
  const { data: classroom } = useClassroom(cid);
  const del = useDeleteFile(fid);

  const [tab, setTab] = useState<Tab>('chat');
  const [showInvite, setShowInvite] = useState(false);

  const isOwner = !!user && classroom?.owner_id === user.id;
  const liveStatus = status?.status ?? file?.processing_status ?? 'pending';
  const ready = liveStatus === 'completed';
  const naiveReady = ready || liveStatus === 'naive_ready';

  const download = async () => {
    try {
      const { download_url } = await fileApi.download(id);
      await Linking.openURL(download_url);
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Could not get download link'));
    }
  };

  const onDelete = async () => {
    try {
      await del.mutateAsync(id);
      toast.success('File deleted');
      router.back();
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Delete failed'));
    }
  };

  if (isLoading || !file) {
    return (
      <Screen className="items-center justify-center" edges={['bottom']}>
        <Stack.Screen options={{ title: 'File' }} />
        <Spinner size="large" />
      </Screen>
    );
  }

  return (
    <Screen edges={['bottom']}>
      <Stack.Screen
        options={{
          title: file.filename,
          headerRight: () => (
            <View className="flex-row items-center gap-4">
              <Pressable onPress={() => setShowInvite(true)} hitSlop={8}>
                <MessageSquarePlus color="#1c69e3" size={20} />
              </Pressable>
              <Pressable onPress={download} hitSlop={8}>
                <Download color="#1c69e3" size={20} />
              </Pressable>
              {isOwner ? (
                <Pressable onPress={onDelete} hitSlop={8}>
                  <Trash2 color="#a20519" size={20} />
                </Pressable>
              ) : null}
            </View>
          ),
        }}
      />
      <View className="flex-1 gap-3 p-4">
        {file.description ? (
          <Text className="text-xs text-muted-foreground" numberOfLines={2}>
            {file.description}
          </Text>
        ) : null}
        <View className="flex-row items-center gap-2">
          <FileStatusBadge status={liveStatus} />
          {!ready && liveStatus !== 'failed' ? <Spinner /> : null}
        </View>

        <Segmented<Tab>
          value={tab}
          onChange={setTab}
          options={[
            { key: 'chat', label: 'Chat' },
            { key: 'quiz', label: 'Quiz' },
            { key: 'flashcards', label: 'Cards' },
            { key: 'mindmap', label: 'Mindmap' },
          ]}
        />

        <View className="flex-1">
          {tab === 'chat' ? (
            naiveReady ? (
              <ChatPanel fileId={id} />
            ) : (
              <Locked text="Chat unlocks once the document reaches “Chat ready.”" />
            )
          ) : tab === 'quiz' ? (
            ready ? (
              <QuizPanel fileId={id} />
            ) : (
              <Locked text="Quizzes unlock once the document is fully processed (“Ready”)." />
            )
          ) : tab === 'flashcards' ? (
            naiveReady ? (
              <FlashcardsPanel fileId={id} />
            ) : (
              <Locked text="Flashcards unlock once the document reaches “Chat ready.”" />
            )
          ) : ready ? (
            <MindmapPanel fileId={id} />
          ) : (
            <Locked text="Mindmaps unlock once the document is fully processed (“Ready”)." />
          )}
        </View>
      </View>
      <InviteDialog fileId={id} visible={showInvite} onClose={() => setShowInvite(false)} />
    </Screen>
  );
}
