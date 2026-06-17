import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Stack, useLocalSearchParams } from 'expo-router';
import { Check } from 'lucide-react-native';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail, folderQuizApi, type FolderQuizQuestionView } from '@/api/sampai';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Screen } from '@/components/ui/screen';
import { Segmented } from '@/components/ui/segmented';
import { Spinner } from '@/components/ui/spinner';
import { useFiles } from '@/features/files/hooks';
import { cn } from '@/lib/utils';

type Diff = 'auto' | 'easy' | 'medium' | 'hard';

function QuestionCard({
  q,
  idx,
  draft,
  setDraft,
  onSubmit,
  submitting,
}: {
  q: FolderQuizQuestionView;
  idx: number;
  draft: string;
  setDraft: (s: string) => void;
  onSubmit: () => void;
  submitting: boolean;
}) {
  return (
    <Card className="gap-2">
      <Text className="font-semibold text-foreground">
        {idx + 1}. {q.question}
      </Text>
      {q.source_file_names.length > 0 ? (
        <Text className="text-xs text-muted-foreground">Sources: {q.source_file_names.join(', ')}</Text>
      ) : null}

      {q.submitted ? (
        <View className="gap-1">
          <Text className={cn('font-semibold', (q.score ?? 0) >= 4 ? 'text-chart-4' : 'text-destructive')}>
            Score: {q.score ?? 0}/5
          </Text>
          {q.user_answer ? <Text className="text-sm text-foreground">Your answer: {q.user_answer}</Text> : null}
          {q.reference_answer ? (
            <Text className="text-sm text-muted-foreground">Reference: {q.reference_answer}</Text>
          ) : null}
          {q.missing.length > 0 ? (
            <Text className="text-xs text-destructive">Missing: {q.missing.join('; ')}</Text>
          ) : null}
          {q.incorrect.length > 0 ? (
            <Text className="text-xs text-destructive">Incorrect: {q.incorrect.join('; ')}</Text>
          ) : null}
          {q.verdict ? <Text className="text-xs text-muted-foreground">{q.verdict}</Text> : null}
        </View>
      ) : (
        <>
          <Input
            placeholder="Type your answer…"
            value={draft}
            onChangeText={setDraft}
            multiline
            className="max-h-32"
          />
          <Button
            label="Submit answer"
            onPress={onSubmit}
            loading={submitting}
            disabled={!draft.trim() || submitting}
          />
        </>
      )}
    </Card>
  );
}

export default function FolderQuizScreen() {
  const { folderId, name } = useLocalSearchParams<{ folderId: string; name?: string; classroomId?: string }>();
  const fid = Number(folderId);
  const qc = useQueryClient();

  const [quizId, setQuizId] = useState<number | null>(null);
  const [diff, setDiff] = useState<Diff>('auto');
  const [selFiles, setSelFiles] = useState<number[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [submittingId, setSubmittingId] = useState<string | null>(null);

  const files = useFiles(fid);
  const completed = (files.data ?? []).filter((f) => f.processing_status === 'completed');

  const history = useQuery({ queryKey: ['fquiz-history', fid], queryFn: () => folderQuizApi.history(fid) });
  useEffect(() => {
    if (quizId == null && history.data?.has_open_quiz && history.data.open_quiz_id) {
      setQuizId(history.data.open_quiz_id);
    }
  }, [history.data, quizId]);

  const quiz = useQuery({
    queryKey: ['fquiz', quizId],
    queryFn: () => folderQuizApi.get(quizId as number),
    enabled: quizId != null,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'pending' || s === 'generating' ? 2500 : false;
    },
  });

  const generate = useMutation({
    mutationFn: () =>
      folderQuizApi.generate(fid, {
        difficulty: diff === 'auto' ? undefined : diff,
        file_ids: selFiles.length ? selFiles : undefined,
      }),
    onSuccess: (r) => {
      setQuizId(r.quiz_id);
      void qc.invalidateQueries({ queryKey: ['fquiz-history', fid] });
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not generate quiz')),
  });

  const submitQ = useMutation({
    mutationFn: (args: { qid: string; ans: string }) =>
      folderQuizApi.submitQuestion(quizId as number, args.qid, args.ans),
    onSuccess: () => void quiz.refetch(),
    onError: (e) => toast.error(apiErrorDetail(e, 'Submit failed')),
  });

  const status = quiz.data?.status;

  const toggleFile = (id: number) =>
    setSelFiles((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  // ── config ──
  if (quizId == null || status === 'failed') {
    return (
      <Screen edges={['bottom']}>
        <Stack.Screen options={{ title: name ?? 'Cross-file quiz' }} />
        <ScrollView contentContainerStyle={{ padding: 24, gap: 14 }}>
          {status === 'failed' ? (
            <Text className="text-destructive">{quiz.data?.error_msg ?? 'Generation failed.'}</Text>
          ) : null}
          <Text className="text-sm text-muted-foreground">
            Generates short-answer questions spanning multiple documents, graded by the tutor.
          </Text>

          <Text className="text-sm font-semibold text-foreground">Difficulty</Text>
          <Segmented
            value={diff}
            onChange={setDiff}
            options={[
              { key: 'auto', label: 'Auto' },
              { key: 'easy', label: 'Easy' },
              { key: 'medium', label: 'Med' },
              { key: 'hard', label: 'Hard' },
            ]}
          />

          <Text className="text-sm font-semibold text-foreground">
            Files {selFiles.length ? `(${selFiles.length} selected)` : '(all)'}
          </Text>
          {completed.length === 0 ? (
            <Text className="text-muted-foreground">No fully-processed files in this folder yet.</Text>
          ) : (
            completed.map((f) => {
              const on = selFiles.includes(f.id);
              return (
                <Pressable key={f.id} onPress={() => toggleFile(f.id)}>
                  <Card className="flex-row items-center justify-between">
                    <Text className="flex-1 text-foreground" numberOfLines={1}>
                      {f.filename}
                    </Text>
                    <View
                      className={cn(
                        'h-5 w-5 items-center justify-center rounded border',
                        on ? 'border-primary bg-primary' : 'border-border',
                      )}
                    >
                      {on ? <Check size={14} color="#f9fcff" /> : null}
                    </View>
                  </Card>
                </Pressable>
              );
            })
          )}

          <Button
            label="Generate quiz"
            onPress={() => generate.mutate()}
            loading={generate.isPending}
            disabled={completed.length === 0 || generate.isPending}
          />
        </ScrollView>
      </Screen>
    );
  }

  // ── generating ──
  if (status === 'pending' || status === 'generating' || quiz.isLoading) {
    return (
      <Screen className="items-center justify-center" edges={['bottom']}>
        <Stack.Screen options={{ title: name ?? 'Cross-file quiz' }} />
        <Spinner size="large" />
        <Text className="mt-3 text-muted-foreground">Generating cross-file quiz…</Text>
      </Screen>
    );
  }

  // ── take / review ──
  const d = quiz.data;
  return (
    <Screen edges={['bottom']}>
      <Stack.Screen options={{ title: name ?? 'Cross-file quiz' }} />
      <ScrollView contentContainerStyle={{ padding: 24, gap: 12 }}>
        {d && d.graded_count > 0 ? (
          <Card className="items-center gap-1">
            <Text className="text-2xl font-bold text-foreground">
              {Math.round((d.score ?? 0) * 100)}%
            </Text>
            <Text className="text-muted-foreground">
              {d.correct_count ?? 0}/{d.total_count} strong · {d.graded_count} graded
            </Text>
          </Card>
        ) : null}

        {(d?.questions ?? []).map((q, idx) => (
          <QuestionCard
            key={q.id}
            q={q}
            idx={idx}
            draft={drafts[q.id] ?? ''}
            setDraft={(s) => setDrafts((m) => ({ ...m, [q.id]: s }))}
            submitting={submitQ.isPending && submittingId === q.id}
            onSubmit={() => {
              setSubmittingId(q.id);
              submitQ.mutate({ qid: q.id, ans: (drafts[q.id] ?? '').trim() });
            }}
          />
        ))}

        {d && d.topic_scores.length > 0 ? (
          <Card className="gap-1">
            <Text className="text-sm font-semibold text-foreground">By document</Text>
            {d.topic_scores.map((t) => (
              <Text key={`${t.file_id}-${t.filename}`} className="text-sm text-muted-foreground">
                {t.filename}: {Math.round(t.mean_score * 100)}% ({t.correct_count}/{t.question_count})
              </Text>
            ))}
          </Card>
        ) : null}
      </ScrollView>
    </Screen>
  );
}
