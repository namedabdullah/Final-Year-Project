import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail, flashcardApi } from '@/api/sampai';
import { tapLight } from '@/lib/haptics';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Segmented } from '@/components/ui/segmented';
import { Spinner } from '@/components/ui/spinner';

type Result = 'forgot' | 'unsure' | 'know';

export function FlashcardsPanel({ fileId }: { fileId: number }) {
  const qc = useQueryClient();
  const [deckId, setDeckId] = useState<number | null>(null);
  const [count, setCount] = useState<'10' | '20' | '30'>('20');
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);

  const history = useQuery({ queryKey: ['deck-history', fileId], queryFn: () => flashcardApi.history(fileId) });

  useEffect(() => {
    if (deckId == null && history.data?.has_open_deck && history.data.open_deck_id) {
      setDeckId(history.data.open_deck_id);
    }
  }, [history.data, deckId]);

  const deck = useQuery({
    queryKey: ['deck', deckId],
    queryFn: () => flashcardApi.getDeck(deckId as number),
    enabled: deckId != null,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'pending' || s === 'generating' ? 2000 : false;
    },
  });

  const generate = useMutation({
    mutationFn: () => flashcardApi.generate(fileId, Number(count) as 10 | 20 | 30),
    onSuccess: (r) => {
      setIndex(0);
      setFlipped(false);
      setDeckId(r.deck_id);
      void qc.invalidateQueries({ queryKey: ['deck-history', fileId] });
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not generate deck')),
  });

  const review = useMutation({
    mutationFn: (args: { cardId: number; result: Result }) => flashcardApi.review(args.cardId, args.result),
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not save review')),
  });

  const cards = deck.data?.cards ?? [];
  const card = cards[index];
  const status = deck.data?.status;

  const rate = (result: Result) => {
    tapLight();
    if (card) review.mutate({ cardId: card.id, result });
    setFlipped(false);
    setIndex((i) => i + 1);
  };

  const reset = () => {
    setDeckId(null);
    setIndex(0);
    setFlipped(false);
  };

  // ── config / start ──
  if (deckId == null || status === 'failed') {
    const boxes = history.data?.box_counts;
    return (
      <ScrollView className="flex-1" contentContainerStyle={{ gap: 14, paddingVertical: 8 }}>
        {status === 'failed' ? (
          <Text className="text-destructive">{deck.data?.error_msg ?? 'Generation failed.'}</Text>
        ) : null}
        <Text className="text-sm font-semibold text-foreground">Number of cards</Text>
        <Segmented
          value={count}
          onChange={setCount}
          options={[
            { key: '10', label: '10' },
            { key: '20', label: '20' },
            { key: '30', label: '30' },
          ]}
        />
        <Button label="Generate deck" onPress={() => generate.mutate()} loading={generate.isPending} />
        {boxes ? (
          <Card className="gap-1">
            <Text className="text-sm font-semibold text-foreground">Leitner boxes</Text>
            <Text className="text-muted-foreground">
              {[1, 2, 3, 4, 5].map((b) => `B${b}: ${boxes[String(b)] ?? 0}`).join('   ')}
            </Text>
          </Card>
        ) : null}
      </ScrollView>
    );
  }

  // ── generating ──
  if (status === 'pending' || status === 'generating' || deck.isLoading) {
    return (
      <View className="flex-1 items-center justify-center gap-3">
        <Spinner size="large" />
        <Text className="text-muted-foreground">Generating flashcards…</Text>
      </View>
    );
  }

  // ── finished deck ──
  if (index >= cards.length) {
    return (
      <View className="flex-1 items-center justify-center gap-4 p-6">
        <Text className="text-xl font-bold text-foreground">Deck complete 🎉</Text>
        <Text className="text-muted-foreground">You reviewed {cards.length} cards.</Text>
        <Button label="New deck" variant="secondary" onPress={reset} />
      </View>
    );
  }

  // ── review a card ──
  return (
    <View className="flex-1 gap-4 py-4">
      <Text className="text-center text-xs text-muted-foreground">
        Card {index + 1} of {cards.length} · {card.card_type} · box {card.box}
      </Text>

      <Pressable onPress={() => setFlipped((f) => !f)} className="flex-1">
        <Card className="flex-1 items-center justify-center gap-3 p-6">
          <Text className="text-center text-lg font-semibold text-foreground">{card.front}</Text>
          {flipped ? (
            <>
              <View className="h-px w-16 bg-border" />
              <Text className="text-center text-base text-muted-foreground">{card.back}</Text>
            </>
          ) : (
            <Text className="text-xs text-muted-foreground">Tap to reveal</Text>
          )}
        </Card>
      </Pressable>

      {flipped ? (
        <View className="flex-row gap-2">
          <Button label="Forgot" variant="destructive" className="flex-1" onPress={() => rate('forgot')} />
          <Button label="Unsure" variant="secondary" className="flex-1" onPress={() => rate('unsure')} />
          <Button label="Know" className="flex-1" onPress={() => rate('know')} />
        </View>
      ) : (
        <Button label="Show answer" variant="outline" onPress={() => setFlipped(true)} />
      )}
    </View>
  );
}
