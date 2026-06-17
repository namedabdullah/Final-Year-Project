import { useQuery } from '@tanstack/react-query';
import { Stack, useLocalSearchParams } from 'expo-router';
import { Send, X } from 'lucide-react-native';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  useColorScheme,
  View,
} from 'react-native';
import Markdown from 'react-native-markdown-display';

import { groupChatApi } from '@/api/sampai';
import { Input } from '@/components/ui/input';
import { Screen } from '@/components/ui/screen';
import { Spinner } from '@/components/ui/spinner';
import { type GroupMessage, useGroupChatSocket } from '@/hooks/use-group-chat-socket';
import { cn } from '@/lib/utils';
import { useRealtime } from '@/stores/realtime';
import { useAuth } from '@/stores/auth';

export default function ThreadScreen() {
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const threadId = Number(id);
  const me = useAuth((s) => s.user);
  const scheme = useColorScheme();
  const fg = scheme === 'dark' ? '#f6f9fb' : '#080c0f';

  const {
    messages,
    typingUsers,
    agentTyping,
    onlineUserIds,
    connected,
    hasMore,
    loadingMore,
    send,
    sendTyping,
    sendReadReceipt,
    loadMore,
  } = useGroupChatSocket(threadId);

  const thread = useQuery({ queryKey: ['thread', threadId], queryFn: () => groupChatApi.thread(threadId) });
  const members = thread.data?.members ?? [];

  const [input, setInput] = useState('');
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [replyTo, setReplyTo] = useState<GroupMessage | null>(null);
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const lastReadRef = useRef(0);

  // auto-scroll on new messages
  useEffect(() => {
    requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
  }, [messages.length]);

  // read receipts + clear unread bump
  useEffect(() => {
    const maxSeq = messages.reduce((mx, m) => (typeof m.seq === 'number' && m.seq > mx ? m.seq : mx), 0);
    if (maxSeq > lastReadRef.current) {
      lastReadRef.current = maxSeq;
      sendReadReceipt(maxSeq);
      groupChatApi.read(threadId, maxSeq).catch(() => {});
      useRealtime.getState().clearUnread(threadId);
    }
  }, [messages, threadId, sendReadReceipt]);

  const mentionOptions = useMemo(() => {
    if (mentionQuery == null) return [];
    const names = ['SAMpai', ...members.map((m) => m.user.username).filter((u) => u !== me?.username)];
    return names.filter((u) => u.toLowerCase().startsWith(mentionQuery)).slice(0, 6);
  }, [mentionQuery, members, me]);

  const onChangeText = (t: string) => {
    setInput(t);
    sendTyping();
    const m = /@(\w*)$/.exec(t);
    setMentionQuery(m ? m[1].toLowerCase() : null);
  };

  const pickMention = (u: string) => {
    setInput((prev) => prev.replace(/@(\w*)$/, `@${u} `));
    setMentionQuery(null);
  };

  const onSend = async () => {
    const content = input.trim();
    if (!content || sending) return;
    setInput('');
    setMentionQuery(null);
    const reply = replyTo;
    setReplyTo(null);
    setSending(true);
    try {
      await send(content, reply && typeof reply.id === 'number' ? reply.id : undefined);
    } finally {
      setSending(false);
    }
  };

  const typingLabel = useMemo(() => {
    const names = typingUsers.filter((t) => t.userId !== me?.id && t.isTyping).map((t) => t.username);
    if (agentTyping) return 'SAMpai is thinking…';
    if (names.length === 1) return `${names[0]} is typing…`;
    if (names.length > 1) return 'Several people are typing…';
    return '';
  }, [typingUsers, agentTyping, me]);

  const findReply = (rid: number | null) =>
    rid ? messages.find((m) => m.id === rid) : undefined;

  return (
    <Screen edges={['bottom']}>
      <Stack.Screen options={{ title: (name as string) ?? 'Group chat' }} />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        <View className="flex-row items-center justify-between px-4 py-1">
          <Text className="text-xs text-muted-foreground">
            {connected ? `${onlineUserIds.length} online` : 'connecting…'}
          </Text>
          {typingLabel ? <Text className="text-xs text-muted-foreground">{typingLabel}</Text> : null}
        </View>

        <ScrollView
          ref={scrollRef}
          className="flex-1"
          contentContainerStyle={{ gap: 8, padding: 12 }}
          keyboardShouldPersistTaps="handled"
        >
          {hasMore ? (
            <Pressable onPress={() => void loadMore()} className="items-center py-2">
              {loadingMore ? <Spinner /> : <Text className="text-xs text-primary">Load earlier messages</Text>}
            </Pressable>
          ) : null}

          {thread.isLoading && messages.length === 0 ? (
            <View className="items-center py-6">
              <Spinner />
            </View>
          ) : null}

          {messages.map((m) => {
            if (m.role === 'system') {
              return (
                <Text key={m.id} className="self-center text-xs text-muted-foreground">
                  {m.content}
                </Text>
              );
            }
            const own = m.role === 'user' && (m.user_id === me?.id || (m.user_id === null && m.seq === -1));
            const isAgent = m.role === 'agent';
            const repliedTo = findReply(m.reply_to_id);
            return (
              <Pressable
                key={m.id}
                onLongPress={() => typeof m.id === 'number' && setReplyTo(m)}
                className={cn(
                  'max-w-[85%] rounded-xl px-3 py-2',
                  own ? 'self-end bg-primary' : isAgent ? 'self-start bg-accent' : 'self-start bg-secondary',
                )}
              >
                {!own ? (
                  <Text className="mb-0.5 text-xs font-semibold text-muted-foreground">
                    {isAgent ? 'SAMpai' : (m.author?.username ?? 'Unknown')}
                  </Text>
                ) : null}
                {repliedTo ? (
                  <Text className="mb-1 border-l-2 border-border pl-2 text-xs text-muted-foreground" numberOfLines={1}>
                    {repliedTo.content}
                  </Text>
                ) : null}
                {m.is_discarded ? (
                  <Text className="text-xs italic text-muted-foreground">message removed</Text>
                ) : own ? (
                  <Text className="text-primary-foreground">{m.content}</Text>
                ) : (
                  <Markdown style={{ body: { color: fg } }}>{m.content}</Markdown>
                )}
              </Pressable>
            );
          })}
        </ScrollView>

        {mentionOptions.length > 0 ? (
          <View className="border-t border-border bg-card">
            {mentionOptions.map((u) => (
              <Pressable key={u} onPress={() => pickMention(u)} className="px-4 py-2">
                <Text className="text-foreground">@{u}</Text>
              </Pressable>
            ))}
          </View>
        ) : null}

        {replyTo ? (
          <View className="flex-row items-center gap-2 border-t border-border px-4 py-2">
            <Text className="flex-1 text-xs text-muted-foreground" numberOfLines={1}>
              Replying to: {replyTo.content}
            </Text>
            <Pressable onPress={() => setReplyTo(null)} hitSlop={8}>
              <X size={16} color="#6a737a" />
            </Pressable>
          </View>
        ) : null}

        <View className="flex-row items-end gap-2 px-3 py-2">
          <View className="flex-1">
            <Input
              placeholder="Message…  (@SAMpai to ask the tutor)"
              value={input}
              onChangeText={onChangeText}
              multiline
              className="max-h-28"
            />
          </View>
          <Pressable
            onPress={onSend}
            disabled={!input.trim() || sending}
            className={cn(
              'h-12 w-12 items-center justify-center rounded-lg bg-primary',
              (!input.trim() || sending) && 'opacity-50',
            )}
          >
            {sending ? <ActivityIndicator color="#f9fcff" /> : <Send color="#f9fcff" size={20} />}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
