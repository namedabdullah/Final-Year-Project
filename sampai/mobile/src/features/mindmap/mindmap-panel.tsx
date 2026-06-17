import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ChevronDown, ChevronRight, Send, Sparkles } from 'lucide-react-native';
import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, useColorScheme, View } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { toast } from 'sonner-native';

import { apiErrorDetail, type MindNode, mindmapApi } from '@/api/sampai';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';

function TreeNode({ node, onSelect }: { node: MindNode; onSelect: (n: MindNode) => void }) {
  const [open, setOpen] = useState(node.depth <= 0);
  const children = node.children ?? [];
  const hasChildren = children.length > 0;
  return (
    <View>
      <View className="flex-row items-center gap-1 py-1">
        {hasChildren ? (
          <Pressable onPress={() => setOpen((o) => !o)} hitSlop={8} className="p-1">
            {open ? (
              <ChevronDown size={16} color="#6a737a" />
            ) : (
              <ChevronRight size={16} color="#6a737a" />
            )}
          </Pressable>
        ) : (
          <View className="w-6" />
        )}
        <Pressable className="flex-1" onPress={() => onSelect(node)}>
          <Text className={cn('text-foreground', node.depth === 0 && 'font-semibold')} numberOfLines={2}>
            {node.topic}
          </Text>
        </Pressable>
      </View>
      {open && hasChildren ? (
        <View className="ml-3 border-l border-border pl-2">
          {children.map((c) => (
            <TreeNode key={c.id} node={c} onSelect={onSelect} />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function NodeView({ mindmapId, node, onBack }: { mindmapId: number; node: MindNode; onBack: () => void }) {
  const scheme = useColorScheme();
  const fg = scheme === 'dark' ? '#f6f9fb' : '#080c0f';
  const [input, setInput] = useState('');

  const chat = useQuery({
    queryKey: ['mindmap-chat', mindmapId],
    queryFn: () => mindmapApi.chatHistory(mindmapId),
    refetchInterval: (q) =>
      q.state.data?.messages?.some((m) => (m.message_metadata as { pending?: boolean })?.pending) ? 1500 : false,
  });

  const ask = useMutation({
    mutationFn: (content: string) => mindmapApi.ask(mindmapId, content, node.id),
    onSuccess: () => void chat.refetch(),
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not ask')),
  });

  const explore = useMutation({
    mutationFn: () => mindmapApi.explore(mindmapId, node.id),
    onSuccess: () => void chat.refetch(),
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not explore')),
  });

  const send = () => {
    const q = input.trim();
    if (!q || ask.isPending) return;
    setInput('');
    ask.mutate(q);
  };

  const messages = (chat.data?.messages ?? []).filter((m) => m.role !== 'marker');

  return (
    <View className="flex-1 gap-3 py-2">
      <Pressable onPress={onBack} hitSlop={8} className="flex-row items-center gap-1">
        <ArrowLeft size={18} color="#1c69e3" />
        <Text className="text-primary">Back to map</Text>
      </Pressable>

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 10, paddingBottom: 8 }}>
        <Text className="text-xl font-bold text-foreground">{node.topic}</Text>
        {node.description ? <Text className="text-muted-foreground">{node.description}</Text> : null}

        <Button
          label="Explore deeper"
          variant="secondary"
          loading={explore.isPending}
          onPress={() => explore.mutate()}
        />

        {messages.map((m) => (
          <View
            key={m.id}
            className={cn(
              'max-w-[90%] rounded-xl px-3 py-2',
              m.role === 'user' ? 'self-end bg-primary' : 'self-start bg-secondary',
            )}
          >
            {m.role === 'user' ? (
              <Text className="text-primary-foreground">{m.content}</Text>
            ) : (m.message_metadata as { pending?: boolean })?.pending && !m.content ? (
              <ActivityIndicator />
            ) : (
              <Markdown style={{ body: { color: fg } }}>{m.content}</Markdown>
            )}
          </View>
        ))}
      </ScrollView>

      <View className="flex-row items-end gap-2">
        <View className="flex-1">
          <Input
            placeholder={`Ask about “${node.topic}”…`}
            value={input}
            onChangeText={setInput}
            multiline
            className="max-h-24"
          />
        </View>
        <Pressable
          onPress={send}
          disabled={!input.trim() || ask.isPending}
          className={cn(
            'h-12 w-12 items-center justify-center rounded-lg bg-primary',
            (!input.trim() || ask.isPending) && 'opacity-50',
          )}
        >
          {ask.isPending ? <ActivityIndicator color="#f9fcff" /> : <Send color="#f9fcff" size={20} />}
        </Pressable>
      </View>
    </View>
  );
}

export function MindmapPanel({ fileId }: { fileId: number }) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<MindNode | null>(null);

  const mm = useQuery({
    queryKey: ['mindmap', fileId],
    queryFn: () => mindmapApi.get(fileId),
    retry: false,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'pending' || s === 'generating' ? 2000 : false;
    },
  });

  const generate = useMutation({
    mutationFn: () => mindmapApi.generate(fileId, false),
    onSuccess: (r) => {
      qc.setQueryData(['mindmap', fileId], r.mindmap);
      void qc.invalidateQueries({ queryKey: ['mindmap', fileId] });
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not start mindmap')),
  });

  if (mm.isLoading) {
    return (
      <View className="flex-1 items-center justify-center">
        <Spinner size="large" />
      </View>
    );
  }

  const mindmap = mm.data;
  const status = mindmap?.status;

  // not generated yet (get 404s) or failed
  if (mm.isError || !mindmap || status === 'failed') {
    return (
      <View className="flex-1 items-center justify-center gap-4 p-6">
        <Text className="text-center text-muted-foreground">
          {status === 'failed'
            ? (mindmap?.error_message ?? 'Mindmap generation failed.')
            : 'No mindmap yet for this document.'}
        </Text>
        <Button label="Generate mindmap" onPress={() => generate.mutate()} loading={generate.isPending} />
      </View>
    );
  }

  if (status === 'pending' || status === 'generating') {
    return (
      <View className="flex-1 items-center justify-center gap-3">
        <Spinner size="large" />
        <Text className="text-muted-foreground">Building the mind map…</Text>
      </View>
    );
  }

  if (selected) {
    return <NodeView mindmapId={mindmap.id} node={selected} onBack={() => setSelected(null)} />;
  }

  const root = mindmap.tree_data?.root;
  return (
    <ScrollView className="flex-1" contentContainerStyle={{ gap: 4, paddingVertical: 8 }}>
      <View className="mb-1 flex-row items-center gap-2">
        <Sparkles size={16} color="#1c69e3" />
        <Text className="text-sm text-muted-foreground">Tap a topic to explore & ask questions</Text>
      </View>
      {root ? <TreeNode node={root} onSelect={setSelected} /> : <Text className="text-muted-foreground">Empty map.</Text>}
    </ScrollView>
  );
}
