import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { fileApi, type UploadFile } from '@/api/sampai';
import { qk } from '@/lib/query-keys';

export function useFiles(folderId: number) {
  return useQuery({
    queryKey: qk.files(folderId),
    queryFn: () => fileApi.list(folderId),
    enabled: Number.isFinite(folderId),
    // Keep refreshing the list while any file is still being processed.
    refetchInterval: (q) => {
      const pending = q.state.data?.some(
        (f) => f.processing_status !== 'completed' && f.processing_status !== 'failed',
      );
      return pending ? 2500 : false;
    },
  });
}

export function useFile(fileId: number) {
  return useQuery({
    queryKey: qk.file(fileId),
    queryFn: () => fileApi.get(fileId),
    enabled: Number.isFinite(fileId),
  });
}

/** Polls processing status every 2.5s until it reaches a terminal state. */
export function useFileStatus(fileId: number, enabled = true) {
  return useQuery({
    queryKey: qk.fileStatus(fileId),
    queryFn: () => fileApi.status(fileId),
    enabled: enabled && Number.isFinite(fileId),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'completed' || s === 'failed' ? false : 2500;
    },
  });
}

export function useUploadFile(folderId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { file: UploadFile; onProgress?: (pct: number) => void }) =>
      fileApi.upload(folderId, args.file, args.onProgress),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.files(folderId) }),
  });
}

export function useDeleteFile(folderId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileId: number) => fileApi.remove(fileId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.files(folderId) }),
  });
}
