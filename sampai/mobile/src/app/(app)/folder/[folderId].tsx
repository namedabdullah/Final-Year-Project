import * as DocumentPicker from 'expo-document-picker';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { FileText } from 'lucide-react-native';
import { useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail } from '@/api/sampai';
import { FileStatusBadge } from '@/components/file-status-badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Screen } from '@/components/ui/screen';
import { Spinner } from '@/components/ui/spinner';
import { useFiles, useUploadFile } from '@/features/files/hooks';

const ACCEPT = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'text/plain',
];

export default function FolderDetail() {
  const { folderId, classroomId, name } = useLocalSearchParams<{
    folderId: string;
    classroomId?: string;
    name?: string;
  }>();
  const fid = Number(folderId);
  const { data: files, isLoading, refetch, isRefetching } = useFiles(fid);
  const upload = useUploadFile(fid);
  const [progress, setProgress] = useState<number | null>(null);

  const pick = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({ type: ACCEPT, copyToCacheDirectory: true });
      if (res.canceled || !res.assets?.[0]) return;
      const a = res.assets[0];
      setProgress(0);
      await upload.mutateAsync({
        file: { uri: a.uri, name: a.name, mimeType: a.mimeType },
        onProgress: setProgress,
      });
      toast.success('Uploaded — processing started');
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Upload failed'));
    } finally {
      setProgress(null);
    }
  };

  return (
    <Screen edges={['bottom']}>
      <Stack.Screen options={{ title: name ?? 'Folder' }} />
      <ScrollView
        contentContainerStyle={{ padding: 24, gap: 12 }}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => void refetch()} />}
      >
        <Button
          label={progress === null ? 'Upload document' : `Uploading… ${progress}%`}
          onPress={pick}
          loading={upload.isPending}
          disabled={upload.isPending}
        />
        <Text className="text-xs text-muted-foreground">PDF, DOCX, PPTX or TXT · up to 100 MB</Text>
        <Button
          label="Cross-file quiz"
          variant="secondary"
          onPress={() =>
            router.push({
              pathname: '/folder-quiz/[folderId]',
              params: { folderId: String(fid), classroomId: classroomId ?? '', name: name ?? 'Folder' },
            })
          }
        />

        {isLoading ? (
          <View className="items-center py-6">
            <Spinner />
          </View>
        ) : (files ?? []).length === 0 ? (
          <Text className="text-muted-foreground">No files yet.</Text>
        ) : (
          (files ?? []).map((f) => (
            <Pressable
              key={f.id}
              onPress={() =>
                router.push({
                  pathname: '/file/[fileId]',
                  params: { fileId: String(f.id), folderId: String(fid), classroomId: classroomId ?? '' },
                })
              }
            >
              <Card className="flex-row items-center gap-3">
                <FileText color="#1c69e3" size={22} />
                <View className="flex-1">
                  <Text className="text-base font-semibold text-foreground" numberOfLines={1}>
                    {f.filename}
                  </Text>
                  <FileStatusBadge status={f.processing_status} />
                </View>
              </Card>
            </Pressable>
          ))
        )}
      </ScrollView>
    </Screen>
  );
}
