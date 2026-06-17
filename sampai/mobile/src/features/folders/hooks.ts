import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { folderApi } from '@/api/sampai';
import { qk } from '@/lib/query-keys';

export function useFolders(classroomId: number) {
  return useQuery({
    queryKey: qk.folders(classroomId),
    queryFn: () => folderApi.list(classroomId),
    enabled: Number.isFinite(classroomId),
  });
}

export function useCreateFolder(classroomId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => folderApi.create(classroomId, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.folders(classroomId) }),
  });
}

export function useDeleteFolder(classroomId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (folderId: number) => folderApi.remove(folderId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.folders(classroomId) }),
  });
}
