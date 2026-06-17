import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react-native';
import { useState } from 'react';
import { Pressable, Text, useColorScheme, useWindowDimensions, View } from 'react-native';
import RenderHtml from 'react-native-render-html';
import { toast } from 'sonner-native';

import { type Announcement, announcementApi, apiErrorDetail } from '@/api/sampai';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';

function AnnouncementCard({
  a,
  width,
  fg,
  isOwner,
  userId,
  onChanged,
}: {
  a: Announcement;
  width: number;
  fg: string;
  isOwner: boolean;
  userId?: number;
  onChanged: () => void;
}) {
  const [comment, setComment] = useState('');
  const addComment = useMutation({
    mutationFn: () => announcementApi.addComment(a.id, comment.trim()),
    onSuccess: () => {
      setComment('');
      onChanged();
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not comment')),
  });
  const removeComment = useMutation({
    mutationFn: (cid: number) => announcementApi.removeComment(a.id, cid),
    onSuccess: onChanged,
    onError: (e) => toast.error(apiErrorDetail(e, 'Delete failed')),
  });
  const del = useMutation({
    mutationFn: () => announcementApi.remove(a.id),
    onSuccess: onChanged,
    onError: (e) => toast.error(apiErrorDetail(e, 'Delete failed')),
  });

  const canDeleteAnn = isOwner || a.created_by_id === userId;

  return (
    <Card className="gap-2">
      <View className="flex-row items-start justify-between">
        <Text className="flex-1 text-xs text-muted-foreground">{a.author?.username ?? 'Unknown'}</Text>
        {canDeleteAnn ? (
          <Pressable onPress={() => del.mutate()} hitSlop={8}>
            <Trash2 size={14} color="#a20519" />
          </Pressable>
        ) : null}
      </View>

      <RenderHtml contentWidth={width - 80} source={{ html: a.content }} baseStyle={{ color: fg }} />

      {a.comments.length > 0 ? (
        <View className="mt-1 gap-1 border-t border-border pt-2">
          {a.comments.map((c) => (
            <View key={c.id} className="flex-row items-start justify-between">
              <Text className="flex-1 text-sm text-foreground">
                <Text className="font-semibold">{c.author?.username ?? 'User'}: </Text>
                {c.content}
              </Text>
              {isOwner || c.created_by_id === userId ? (
                <Pressable onPress={() => removeComment.mutate(c.id)} hitSlop={8}>
                  <Trash2 size={12} color="#a20519" />
                </Pressable>
              ) : null}
            </View>
          ))}
        </View>
      ) : null}

      <View className="flex-row items-end gap-2">
        <View className="flex-1">
          <Input placeholder="Add a comment…" value={comment} onChangeText={setComment} />
        </View>
        <Button
          label="Send"
          onPress={() => addComment.mutate()}
          loading={addComment.isPending}
          disabled={!comment.trim() || addComment.isPending}
        />
      </View>
    </Card>
  );
}

export function AnnouncementsPanel({
  classroomId,
  isOwner,
  userId,
}: {
  classroomId: number;
  isOwner: boolean;
  userId?: number;
}) {
  const qc = useQueryClient();
  const { width } = useWindowDimensions();
  const scheme = useColorScheme();
  const fg = scheme === 'dark' ? '#f6f9fb' : '#080c0f';

  const { data, isLoading } = useQuery({
    queryKey: ['announcements', classroomId],
    queryFn: () => announcementApi.list(classroomId),
  });
  const [content, setContent] = useState('');
  const inv = () => void qc.invalidateQueries({ queryKey: ['announcements', classroomId] });

  const create = useMutation({
    mutationFn: () => announcementApi.create(classroomId, content.trim()),
    onSuccess: () => {
      setContent('');
      inv();
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not post')),
  });

  return (
    <View className="gap-3">
      {isOwner ? (
        <Card className="gap-2">
          <Input
            placeholder="Write an announcement…"
            value={content}
            onChangeText={setContent}
            multiline
            className="max-h-32"
          />
          <Button
            label="Post"
            loading={create.isPending}
            disabled={!content.trim() || create.isPending}
            onPress={() => create.mutate()}
          />
        </Card>
      ) : null}

      {isLoading ? (
        <View className="items-center py-6">
          <Spinner />
        </View>
      ) : (data ?? []).length === 0 ? (
        <Text className="text-muted-foreground">No announcements yet.</Text>
      ) : (
        (data ?? []).map((a) => (
          <AnnouncementCard key={a.id} a={a} width={width} fg={fg} isOwner={isOwner} userId={userId} onChanged={inv} />
        ))
      )}
    </View>
  );
}
