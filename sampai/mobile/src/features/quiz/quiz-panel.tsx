import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail, quizApi, type SubmitAnswer } from '@/api/sampai';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Segmented } from '@/components/ui/segmented';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';

type Diff = 'auto' | 'easy' | 'medium' | 'hard';

export function QuizPanel({ fileId }: { fileId: number }) {
  const qc = useQueryClient();
  const [quizId, setQuizId] = useState<number | null>(null);
  const [num, setNum] = useState<'5' | '10' | '15'>('10');
  const [diff, setDiff] = useState<Diff>('auto');
  const [answers, setAnswers] = useState<Record<string, number | boolean>>({});

  const history = useQuery({ queryKey: ['quiz-history', fileId], queryFn: () => quizApi.history(fileId) });

  useEffect(() => {
    if (quizId == null && history.data?.has_open_quiz && history.data.open_quiz_id) {
      setQuizId(history.data.open_quiz_id);
    }
  }, [history.data, quizId]);

  const quiz = useQuery({
    queryKey: ['quiz', quizId],
    queryFn: () => quizApi.get(quizId as number),
    enabled: quizId != null,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'pending' || s === 'generating' ? 2000 : false;
    },
  });

  const generate = useMutation({
    mutationFn: () =>
      quizApi.generate(fileId, {
        num_questions: Number(num) as 5 | 10 | 15,
        difficulty: diff === 'auto' ? undefined : diff,
      }),
    onSuccess: (r) => {
      setAnswers({});
      setQuizId(r.quiz_id);
      void qc.invalidateQueries({ queryKey: ['quiz-history', fileId] });
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not generate quiz')),
  });

  const submit = useMutation({
    mutationFn: () => {
      const payload: SubmitAnswer[] = (quiz.data?.questions ?? []).map((q) =>
        q.type === 'tf'
          ? { question_id: q.id, answer_bool: typeof answers[q.id] === 'boolean' ? (answers[q.id] as boolean) : undefined }
          : { question_id: q.id, answer_index: typeof answers[q.id] === 'number' ? (answers[q.id] as number) : undefined },
      );
      return quizApi.submit(quizId as number, payload);
    },
    onSuccess: () => {
      void quiz.refetch();
      void qc.invalidateQueries({ queryKey: ['quiz-history', fileId] });
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Submit failed')),
  });

  const reset = () => {
    setQuizId(null);
    setAnswers({});
  };

  const status = quiz.data?.status;

  // ── config / start ──
  if (quizId == null || status === 'failed') {
    return (
      <ScrollView className="flex-1" contentContainerStyle={{ gap: 14, paddingVertical: 8 }}>
        {status === 'failed' ? (
          <Text className="text-destructive">{quiz.data?.error_msg ?? 'Quiz generation failed.'}</Text>
        ) : null}
        <Text className="text-sm font-semibold text-foreground">Number of questions</Text>
        <Segmented
          value={num}
          onChange={setNum}
          options={[
            { key: '5', label: '5' },
            { key: '10', label: '10' },
            { key: '15', label: '15' },
          ]}
        />
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
        <Button label="Generate quiz" onPress={() => generate.mutate()} loading={generate.isPending} />

        {(history.data?.items ?? []).filter((i) => i.status === 'submitted').length > 0 ? (
          <View className="mt-2 gap-2">
            <Text className="text-sm font-semibold text-foreground">Past attempts</Text>
            {(history.data?.items ?? [])
              .filter((i) => i.status === 'submitted')
              .slice(0, 5)
              .map((i) => (
                <Card key={i.quiz_id} className="flex-row justify-between">
                  <Text className="text-muted-foreground">
                    {i.num_questions} Qs · {i.difficulty}
                  </Text>
                  <Text className="font-semibold text-foreground">
                    {i.correct_count ?? 0}/{i.num_questions}
                  </Text>
                </Card>
              ))}
          </View>
        ) : null}
      </ScrollView>
    );
  }

  // ── generating ──
  if (status === 'pending' || status === 'generating' || quiz.isLoading) {
    return (
      <View className="flex-1 items-center justify-center gap-3">
        <Spinner size="large" />
        <Text className="text-muted-foreground">Generating your quiz…</Text>
      </View>
    );
  }

  // ── review (submitted) ──
  if (status === 'submitted' && quiz.data?.review) {
    const r = quiz.data.review;
    return (
      <ScrollView className="flex-1" contentContainerStyle={{ gap: 12, paddingVertical: 8 }}>
        <Card className="items-center gap-1">
          <Text className="text-3xl font-bold text-foreground">
            {r.correct_count}/{r.total_count}
          </Text>
          <Text className="text-muted-foreground">{Math.round(r.score * 100)}% correct</Text>
        </Card>
        {r.answers.map((a, idx) => (
          <Card key={a.id} className="gap-2">
            <Text className="font-semibold text-foreground">
              {idx + 1}. {a.question}
            </Text>
            {a.type === 'mcq' ? (
              a.options.map((opt, oi) => {
                const isCorrect = a.correct_answer === oi;
                const isUser = a.user_answer === oi;
                return (
                  <Text
                    key={oi}
                    className={cn(
                      'text-sm',
                      isCorrect ? 'text-chart-4' : isUser ? 'text-destructive' : 'text-muted-foreground',
                    )}
                  >
                    {isCorrect ? '✓ ' : isUser ? '✗ ' : '  '}
                    {opt}
                  </Text>
                );
              })
            ) : (
              <Text className={cn('text-sm', a.correct ? 'text-chart-4' : 'text-destructive')}>
                Correct answer: {String(a.correct_answer)} · you said {String(a.user_answer)}
              </Text>
            )}
            <Text className="text-xs text-muted-foreground">{a.explanation}</Text>
          </Card>
        ))}
        <Button label="New quiz" variant="secondary" onPress={reset} />
      </ScrollView>
    );
  }

  // ── take (ready) ──
  const questions = quiz.data?.questions ?? [];
  const allAnswered = questions.every((q) => answers[q.id] !== undefined);
  return (
    <ScrollView className="flex-1" contentContainerStyle={{ gap: 12, paddingVertical: 8 }}>
      {questions.map((q, idx) => (
        <Card key={q.id} className="gap-2">
          <Text className="font-semibold text-foreground">
            {idx + 1}. {q.question}
          </Text>
          {q.type === 'mcq' ? (
            q.options.map((opt, oi) => {
              const selected = answers[q.id] === oi;
              return (
                <Pressable
                  key={oi}
                  onPress={() => setAnswers((a) => ({ ...a, [q.id]: oi }))}
                  className={cn(
                    'rounded-lg border px-3 py-2',
                    selected ? 'border-primary bg-secondary' : 'border-border',
                  )}
                >
                  <Text className="text-foreground">{opt}</Text>
                </Pressable>
              );
            })
          ) : (
            <View className="flex-row gap-3">
              {[true, false].map((v) => {
                const selected = answers[q.id] === v;
                return (
                  <Pressable
                    key={String(v)}
                    onPress={() => setAnswers((a) => ({ ...a, [q.id]: v }))}
                    className={cn(
                      'flex-1 items-center rounded-lg border px-3 py-2',
                      selected ? 'border-primary bg-secondary' : 'border-border',
                    )}
                  >
                    <Text className="text-foreground">{v ? 'True' : 'False'}</Text>
                  </Pressable>
                );
              })}
            </View>
          )}
        </Card>
      ))}
      <Button
        label="Submit"
        onPress={() => submit.mutate()}
        loading={submit.isPending}
        disabled={!allAnswered || submit.isPending}
      />
    </ScrollView>
  );
}
