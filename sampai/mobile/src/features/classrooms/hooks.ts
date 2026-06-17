import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { classroomApi } from '@/api/sampai';
import { qk } from '@/lib/query-keys';

export function useClassrooms() {
  return useQuery({ queryKey: qk.classrooms, queryFn: classroomApi.list });
}

export function useClassroom(id: number) {
  return useQuery({
    queryKey: qk.classroom(id),
    queryFn: () => classroomApi.get(id),
    enabled: Number.isFinite(id),
  });
}

export function useCreateClassroom() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string }) => classroomApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.classrooms }),
  });
}

export function useJoinClassroom() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => classroomApi.join(code),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.classrooms }),
  });
}

export function useLeaveClassroom() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => classroomApi.leave(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.classrooms }),
  });
}

export function useDeleteClassroom() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => classroomApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.classrooms }),
  });
}
