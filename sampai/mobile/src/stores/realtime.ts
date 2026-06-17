import { create } from 'zustand';
import { toast } from 'sonner-native';

import { groupChatApi, type GroupInvite, type WsEvent, wsUrl } from '@/api/sampai';

// Ported from sampai/frontend/src/stores/realtime.ts (sonner -> sonner-native).

export interface AnnNotice {
  announcementId: number;
  classroomId: number;
  by: string;
  kind: 'announcement' | 'comment';
}

interface RealtimeState {
  invites: GroupInvite[];
  unread: Record<number, number>; // thread_id -> bump count (mentions while away)
  announcements: AnnNotice[];
  connected: boolean;
  setInvites: (i: GroupInvite[]) => void;
  removeInvite: (id: number) => void;
  clearUnread: (threadId: number) => void;
  clearClassroomAnnouncements: (classroomId: number) => void;
}

export const useRealtime = create<RealtimeState>((set) => ({
  invites: [],
  unread: {},
  announcements: [],
  connected: false,
  setInvites: (invites) => set({ invites }),
  removeInvite: (id) => set((s) => ({ invites: s.invites.filter((x) => x.id !== id) })),
  clearUnread: (threadId) =>
    set((s) => {
      if (!s.unread[threadId]) return s;
      const next = { ...s.unread };
      delete next[threadId];
      return { unread: next };
    }),
  clearClassroomAnnouncements: (classroomId) =>
    set((s) => {
      if (!s.announcements.some((a) => a.classroomId === classroomId)) return s;
      return { announcements: s.announcements.filter((a) => a.classroomId !== classroomId) };
    }),
}));

// Singleton /ws/user connection (outside store state to avoid re-renders).
let ws: WebSocket | null = null;
let stopped = false;
let retry = 0;

export function connectUserSocket(): void {
  stopped = false;
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

  // Seed pending invites so the badge is correct before any live event.
  groupChatApi
    .pendingInvites()
    .then((inv) => useRealtime.getState().setInvites(inv))
    .catch(() => {});

  const open = () => {
    if (stopped) return;
    const sock = new WebSocket(wsUrl('/api/sampai/group-chat/ws/user'));
    ws = sock;
    sock.onopen = () => {
      retry = 0;
      useRealtime.setState({ connected: true });
    };
    sock.onmessage = (ev) => {
      try {
        handle(JSON.parse(ev.data as string) as WsEvent);
      } catch {
        /* ignore malformed frame */
      }
    };
    sock.onclose = () => {
      useRealtime.setState({ connected: false });
      ws = null;
      if (!stopped) {
        retry = Math.min(retry + 1, 6);
        setTimeout(open, 500 * 2 ** (retry - 1)); // 0.5s → 16s backoff
      }
    };
    sock.onerror = () => {
      try {
        sock.close();
      } catch {
        /* noop */
      }
    };
  };
  open();
}

export function disconnectUserSocket(): void {
  stopped = true;
  if (ws) {
    try {
      ws.close();
    } catch {
      /* noop */
    }
    ws = null;
  }
}

function handle(e: WsEvent): void {
  const st = useRealtime.getState();
  switch (e.type) {
    case 'invite_new':
      st.setInvites([e.invite, ...st.invites.filter((x) => x.id !== e.invite.id)]);
      toast(`${e.invite.inviter.username} invited you to a group chat`);
      break;
    case 'invite_cancelled':
      st.removeInvite(e.invite_id);
      break;
    case 'invite_accepted':
      toast.success('Your group-chat invite was accepted');
      break;
    case 'thread_unread_bump':
      useRealtime.setState((s) => ({
        unread: { ...s.unread, [e.thread_id]: (s.unread[e.thread_id] ?? 0) + (e.unread_count ?? 1) },
      }));
      toast('You were mentioned in a discussion');
      break;
    case 'announcement_new':
      useRealtime.setState((s) => ({
        announcements: [
          { announcementId: e.announcement_id, classroomId: e.classroom_id, by: e.author, kind: 'announcement' },
          ...s.announcements.filter((a) => a.announcementId !== e.announcement_id),
        ],
      }));
      toast(`${e.author} posted an announcement`);
      break;
    case 'comment_new':
      useRealtime.setState((s) => ({
        announcements: [
          { announcementId: e.announcement_id, classroomId: e.classroom_id, by: e.author, kind: 'comment' },
          ...s.announcements,
        ],
      }));
      toast(`${e.author} commented on your announcement`);
      break;
    default:
      break;
  }
}
