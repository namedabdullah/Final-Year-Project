// Minimal logout event bus so the axios 401 interceptor can trigger a global
// sign-out without importing navigation/store layers (avoids circular deps).
type Handler = () => void;

const handlers = new Set<Handler>();

export const authEvents = {
  onLogout(handler: Handler): () => void {
    handlers.add(handler);
    return () => handlers.delete(handler);
  },
  emitLogout(): void {
    handlers.forEach((h) => h());
  },
};
