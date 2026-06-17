import { useQuery } from '@tanstack/react-query';
import { Send, Trash2 } from 'lucide-react-native';
import { useEffect, useRef, useState } from 'react';
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
import { toast } from 'sonner-native';

import { apiErrorDetail, chatApi, streamChat } from '@/api/sampai';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

type Msg = { id: string; role: 'user' | 'assistant'; content: string; pending?: boolean };

export function ChatPanel({ fileId }: { fileId: number }) {
  const scheme = useColorScheme();
  const fg = scheme === 'dark' ? '#f6f9fb' : '#080c0f';

  const { data, isLoading } = useQuery({
    queryKey: ['chat', fileId],
    queryFn: () => chatApi.history(fileId),
  });

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (data?.messages) {
      setMessages(
        data.messages
          .filter((m) => m.role !== 'system')
          .map((m) => ({ id: String(m.id), role: m.role as 'user' | 'assistant', content: m.content })),
      );
    }
  }, [data]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const scrollToEnd = () => requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));

  const send = async () => {
    const q = input.trim();
    if (!q || streaming) return;
    setInput('');
    const aId = `a-${q.length}-${messages.length}`;
    setMessages((m) => [
      ...m,
      { id: `u-${m.length}`, role: 'user', content: q },
      { id: aId, role: 'assistant', content: '', pending: true },
    ]);
    setStreaming(true);
    scrollToEnd();

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await streamChat(
        fileId,
        q,
        (tok) => {
          setMessages((m) =>
            m.map((msg) => (msg.id === aId ? { ...msg, content: msg.content + tok, pending: false } : msg)),
          );
          scrollToEnd();
        },
        ctrl.signal,
      );
    } catch (e) {
      const detail = apiErrorDetail(e, 'Chat failed');
      setMessages((m) =>
        m.map((msg) =>
          msg.id === aId ? { ...msg, content: msg.content || `⚠️ ${detail}`, pending: false } : msg,
        ),
      );
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const clear = async () => {
    try {
      await chatApi.clear(fileId);
      setMessages([]);
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Could not clear history'));
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      <View className="flex-row items-center justify-between py-2">
        <Text className="text-sm font-semibold text-foreground">Chat with this document</Text>
        <Pressable hitSlop={8} onPress={clear}>
          <Trash2 color="#a20519" size={16} />
        </Pressable>
      </View>

      <ScrollView
        ref={scrollRef}
        className="flex-1"
        contentContainerStyle={{ gap: 10, paddingVertical: 8 }}
        onContentSizeChange={scrollToEnd}
        keyboardShouldPersistTaps="handled"
      >
        {isLoading ? <ActivityIndicator /> : null}
        {messages.length === 0 && !isLoading ? (
          <Text className="text-muted-foreground">Ask a question about this document.</Text>
        ) : null}
        {messages.map((m) => (
          <View
            key={m.id}
            className={cn(
              'max-w-[85%] rounded-xl px-3 py-2',
              m.role === 'user' ? 'self-end bg-primary' : 'self-start bg-secondary',
            )}
          >
            {m.role === 'user' ? (
              <Text className="text-primary-foreground">{m.content}</Text>
            ) : m.pending && !m.content ? (
              <ActivityIndicator />
            ) : (
              <Markdown style={{ body: { color: fg } }}>{m.content}</Markdown>
            )}
          </View>
        ))}
      </ScrollView>

      <View className="flex-row items-end gap-2 py-2">
        <View className="flex-1">
          <Input placeholder="Ask a question…" value={input} onChangeText={setInput} multiline className="max-h-28" />
        </View>
        <Pressable
          onPress={send}
          disabled={!input.trim() || streaming}
          className={cn(
            'h-12 w-12 items-center justify-center rounded-lg bg-primary',
            (!input.trim() || streaming) && 'opacity-50',
          )}
        >
          {streaming ? <ActivityIndicator color="#f9fcff" /> : <Send color="#f9fcff" size={20} />}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}
