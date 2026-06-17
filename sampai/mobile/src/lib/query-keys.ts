// Centralized TanStack Query keys.
export const qk = {
  classrooms: ['classrooms'] as const,
  classroom: (id: number) => ['classroom', id] as const,
  folders: (classroomId: number) => ['folders', classroomId] as const,
  files: (folderId: number) => ['files', folderId] as const,
  file: (id: number) => ['file', id] as const,
  fileStatus: (id: number) => ['file-status', id] as const,
};
