import { fetch as expoFetch } from 'expo/fetch';

import { Config } from '@/config';
import { getToken } from '@/lib/token';
import type { Classroom, FileItem, Folder, TokenResponse, User } from '@/lib/types';

import api from './client';

// Ported from sampai/frontend/src/api/sampai.ts. Grows phase-by-phase as more
// endpoint groups are added (chat, quiz, flashcards, mindmap, group chat, …).
export const P = '/api/sampai';

// ── health ──
export const healthApi = {
  check: (): Promise<Record<string, unknown>> => api.get(`${P}/health`).then((r) => r.data),
};

// ── auth ──
export const authApi = {
  signup: (body: { username: string; email: string; password: string }): Promise<User> =>
    api.post(`${P}/auth/signup`, body).then((r) => r.data),
  login: (body: { email: string; password: string }): Promise<TokenResponse> =>
    api.post(`${P}/auth/login`, body).then((r) => r.data),
  me: (): Promise<User> => api.get(`${P}/auth/me`).then((r) => r.data),
};

// ── classrooms ──
export const classroomApi = {
  list: (): Promise<Classroom[]> => api.get(`${P}/classrooms`).then((r) => r.data),
  get: (id: number): Promise<Classroom> => api.get(`${P}/classrooms/${id}`).then((r) => r.data),
  create: (body: { name: string; description?: string }): Promise<Classroom> =>
    api.post(`${P}/classrooms`, body).then((r) => r.data),
  join: (code: string): Promise<Classroom> =>
    api.post(`${P}/classrooms/join/${code}`).then((r) => r.data),
  leave: (id: number): Promise<void> =>
    api.post(`${P}/classrooms/${id}/leave`).then(() => undefined),
  remove: (id: number): Promise<void> => api.delete(`${P}/classrooms/${id}`).then(() => undefined),
};

// ── folders ──
export const folderApi = {
  list: (classroomId: number): Promise<Folder[]> =>
    api.get(`${P}/folders/classroom/${classroomId}`).then((r) => r.data),
  create: (classroomId: number, name: string): Promise<Folder> =>
    api.post(`${P}/folders/classroom/${classroomId}`, { name }).then((r) => r.data),
  remove: (folderId: number): Promise<void> =>
    api.delete(`${P}/folders/${folderId}`).then(() => undefined),
};

// ── files ──
export interface FileStatus {
  file_id: number;
  filename: string;
  status: 'pending' | 'processing' | 'naive_ready' | 'completed' | 'failed';
  stage: string | null;
  processed_at: string | null;
}

/** A picked document, shaped for React Native's FormData. */
export interface UploadFile {
  uri: string;
  name: string;
  mimeType?: string;
}

export const fileApi = {
  list: (folderId: number): Promise<FileItem[]> =>
    api.get(`${P}/files/folder/${folderId}`).then((r) => r.data),
  get: (fileId: number): Promise<FileItem> => api.get(`${P}/files/${fileId}`).then((r) => r.data),
  status: (fileId: number): Promise<FileStatus> =>
    api.get(`${P}/files/${fileId}/status`).then((r) => r.data),
  upload: (folderId: number, file: UploadFile, onProgress?: (pct: number) => void): Promise<FileItem> => {
    const form = new FormData();
    // RN FormData file shape ({ uri, name, type }); backend field name is 'upload'.
    form.append('upload', {
      uri: file.uri,
      name: file.name,
      type: file.mimeType ?? 'application/octet-stream',
    } as unknown as Blob);
    return api
      .post(`${P}/files/upload/${folderId}`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total));
        },
      })
      .then((r) => r.data);
  },
  reprocess: (fileId: number): Promise<void> =>
    api.post(`${P}/files/${fileId}/reprocess`).then(() => undefined),
  download: (fileId: number): Promise<{ download_url: string }> =>
    api.get(`${P}/files/${fileId}/download`).then((r) => r.data),
  remove: (fileId: number): Promise<void> =>
    api.delete(`${P}/files/${fileId}`).then(() => undefined),
};

// ── chat (SSE streaming) ──
export interface ChatMessageDTO {
  id: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

export const chatApi = {
  history: (fileId: number): Promise<{ messages: ChatMessageDTO[] }> =>
    api.get(`${P}/chat/files/${fileId}/history`).then((r) => r.data),
  clear: (fileId: number): Promise<void> =>
    api.delete(`${P}/chat/files/${fileId}/history`).then(() => undefined),
};

/**
 * Stream a grounded answer over SSE. Ported from the web streamChat; uses
 * expo/fetch because React Native's core fetch cannot stream response bodies.
 * Calls onToken for each chunk and resolves when the stream ends.
 */
export async function streamChat(
  fileId: number,
  question: string,
  onToken: (t: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await expoFetch(`${Config.API_BASE}/api/sampai/chat/files/${fileId}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken() ?? ''}` },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Chat request failed (${res.status})`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const events = buf.split('\n\n');
    buf = events.pop() ?? '';
    for (const evt of events) {
      const line = evt.trim();
      if (!line.startsWith('data:')) continue;
      try {
        const payload = JSON.parse(line.slice(5).trim()) as { token?: string };
        if (payload.token) onToken(payload.token);
      } catch {
        /* ignore malformed keep-alive lines */
      }
    }
  }
}

// ── quizzes (per-file) ──
export interface QuizQuestionPublic {
  id: string;
  type: 'mcq' | 'tf';
  question: string;
  options: string[];
}
export interface QuizAnswerReview {
  id: string;
  type: 'mcq' | 'tf';
  question: string;
  options: string[];
  user_answer: number | boolean | null;
  correct_answer: number | boolean;
  correct: boolean;
  explanation: string;
}
export interface QuizAttemptResult {
  score: number;
  correct_count: number;
  total_count: number;
  answers: QuizAnswerReview[];
  submitted_at: string | null;
}
export interface QuizDetail {
  quiz_id: number;
  status: 'pending' | 'generating' | 'ready' | 'failed' | 'submitted';
  difficulty: string;
  difficulty_source: string;
  num_questions: number;
  error_msg: string | null;
  questions: QuizQuestionPublic[] | null;
  review: QuizAttemptResult | null;
}
export interface QuizHistoryItem {
  quiz_id: number;
  difficulty: string;
  num_questions: number;
  status: string;
  score: number | null;
  correct_count: number | null;
  submitted_at: string | null;
  created_at: string;
  ready_at: string | null;
}
export interface QuizHistoryResponse {
  items: QuizHistoryItem[];
  has_open_quiz: boolean;
  open_quiz_id: number | null;
}
export interface SubmitAnswer {
  question_id: string;
  answer_index?: number;
  answer_bool?: boolean;
}

const QZ = `${P}/quiz`;
export const quizApi = {
  generate: (
    fileId: number,
    body: { num_questions: 5 | 10 | 15; difficulty?: 'easy' | 'medium' | 'hard' },
  ): Promise<{ quiz_id: number; status: string }> =>
    api.post(`${QZ}/files/${fileId}/generate`, body).then((r) => r.data),
  get: (quizId: number): Promise<QuizDetail> => api.get(`${QZ}/${quizId}`).then((r) => r.data),
  submit: (quizId: number, answers: SubmitAnswer[]): Promise<QuizAttemptResult> =>
    api.post(`${QZ}/${quizId}/submit`, { answers }).then((r) => r.data),
  history: (fileId: number): Promise<QuizHistoryResponse> =>
    api.get(`${QZ}/files/${fileId}/history`).then((r) => r.data),
};

// ── flashcards ──
export interface Card {
  id: number;
  front: string;
  back: string;
  card_type: 'definition' | 'concept' | 'example' | 'formula';
  box: number;
  next_review_at: string;
}
export interface Deck {
  deck_id: number;
  status: 'pending' | 'generating' | 'ready' | 'failed';
  card_count: number | null;
  error_msg: string | null;
  cards: Card[] | null;
}
export interface DeckHistory {
  items: { deck_id: number; status: string; card_count: number | null }[];
  box_counts: Record<string, number> | null;
  has_open_deck: boolean;
  open_deck_id: number | null;
}
export const flashcardApi = {
  generate: (fileId: number, cardCount: 10 | 20 | 30): Promise<{ deck_id: number; status: string }> =>
    api.post(`${P}/flashcards/files/${fileId}/generate`, { card_count: cardCount }).then((r) => r.data),
  getDeck: (deckId: number): Promise<Deck> => api.get(`${P}/flashcards/${deckId}`).then((r) => r.data),
  due: (fileId: number): Promise<{ cards: Card[]; total_due: number }> =>
    api.get(`${P}/flashcards/files/${fileId}/due`).then((r) => r.data),
  history: (fileId: number): Promise<DeckHistory> =>
    api.get(`${P}/flashcards/files/${fileId}/history`).then((r) => r.data),
  review: (cardId: number, result: 'know' | 'unsure' | 'forgot'): Promise<{ box: number }> =>
    api.post(`${P}/flashcards/cards/${cardId}/review`, { result }).then((r) => r.data),
};

// ── mindmap ──
export interface MindNode {
  id: string;
  topic: string;
  description: string;
  depth: number;
  has_children?: boolean;
  children: MindNode[];
}
export interface Mindmap {
  id: number;
  status: 'pending' | 'generating' | 'ready' | 'failed';
  root_topic: string | null;
  tree_data: { version: number; root: MindNode } | null;
  node_count: number;
  error_message: string | null;
}
export interface MindChatMsg {
  id: number;
  node_id: string | null;
  role: 'user' | 'assistant' | 'marker';
  content: string;
  message_metadata: Record<string, unknown>;
}
export const mindmapApi = {
  generate: (fileId: number, force = false): Promise<{ detail: string; mindmap: Mindmap }> =>
    api.post(`${P}/mindmap/files/${fileId}/generate`, { force }).then((r) => r.data),
  get: (fileId: number): Promise<Mindmap> => api.get(`${P}/mindmap/files/${fileId}`).then((r) => r.data),
  explore: (mindmapId: number, nodeId: string): Promise<{ already_explored: boolean }> =>
    api.post(`${P}/mindmap/${mindmapId}/nodes/${nodeId}/explore`).then((r) => r.data),
  chatHistory: (mindmapId: number): Promise<{ messages: MindChatMsg[] }> =>
    api.get(`${P}/mindmap/${mindmapId}/chat`).then((r) => r.data),
  ask: (mindmapId: number, content: string, activeNodeId: string | null): Promise<{ message: MindChatMsg }> =>
    api.post(`${P}/mindmap/${mindmapId}/chat/ask`, { content, active_node_id: activeNodeId }).then((r) => r.data),
};

// ── group chat ──
export interface UserSummary {
  id: number;
  username: string;
}
export interface GroupMember {
  user_id: number;
  role: 'owner' | 'member';
  joined_at: string;
  last_read_seq: number;
  user: UserSummary;
}
export interface GroupChat {
  id: number;
  file_id: number;
  classroom_id: number;
  created_by: number | null;
  name: string | null;
  is_archived: boolean;
  created_at: string;
  members: GroupMember[];
}
export interface ThreadListItem {
  id: number;
  file_id: number;
  classroom_id: number;
  name: string | null;
  is_archived: boolean;
  unread_count: number;
  last_message_preview: string | null;
}
export interface GroupInvite {
  id: number;
  group_chat_id: number;
  inviter_id: number;
  invitee_id: number;
  status: 'pending' | 'accepted' | 'rejected' | 'expired' | 'cancelled';
  created_at: string;
  responded_at: string | null;
  inviter: UserSummary;
  invitee: UserSummary;
}
export interface MentionRef {
  kind: 'agent' | 'user';
  user_id?: number;
  username?: string;
}
export interface GroupMessage {
  id: number;
  group_chat_id: number;
  seq: number;
  user_id: number | null;
  role: 'user' | 'agent' | 'system';
  content: string;
  mentions: MentionRef[];
  reply_to_id: number | null;
  is_discarded: boolean;
  created_at: string;
  author: UserSummary | null;
}

const G = `${P}/group-chat`;
export const groupChatApi = {
  threads: (): Promise<ThreadListItem[]> => api.get(`${G}/threads`).then((r) => r.data),
  thread: (id: number): Promise<GroupChat> => api.get(`${G}/threads/${id}`).then((r) => r.data),
  messages: (id: number, beforeSeq?: number, limit = 50): Promise<GroupMessage[]> =>
    api.get(`${G}/threads/${id}/messages`, { params: { before_seq: beforeSeq, limit } }).then((r) => r.data),
  send: (
    id: number,
    body: { content: string; reply_to_id?: number | null; client_msg_id?: string },
  ): Promise<GroupMessage> => api.post(`${G}/threads/${id}/messages`, body).then((r) => r.data),
  leave: (id: number): Promise<void> => api.post(`${G}/threads/${id}/leave`).then(() => undefined),
  read: (id: number, lastSeq: number): Promise<void> =>
    api.post(`${G}/threads/${id}/read`, { last_seq: lastSeq }).then(() => undefined),
  eligible: (fileId: number, groupChatId?: number): Promise<UserSummary[]> =>
    api
      .get(`${G}/files/${fileId}/eligible-invitees`, { params: { group_chat_id: groupChatId } })
      .then((r) => r.data),
  invite: (
    fileId: number,
    userIds: number[],
    groupChatId?: number,
  ): Promise<{ group_chat_id: number; invites: GroupInvite[] }> =>
    api
      .post(`${G}/files/${fileId}/invite`, { user_ids: userIds, group_chat_id: groupChatId ?? null })
      .then((r) => r.data),
  pendingInvites: (): Promise<GroupInvite[]> => api.get(`${G}/invites/pending`).then((r) => r.data),
  accept: (inviteId: number): Promise<GroupChat> =>
    api.post(`${G}/invites/${inviteId}/accept`).then((r) => r.data),
  reject: (inviteId: number): Promise<GroupInvite> =>
    api.post(`${G}/invites/${inviteId}/reject`).then((r) => r.data),
  cancel: (inviteId: number): Promise<GroupInvite> =>
    api.post(`${G}/invites/${inviteId}/cancel`).then((r) => r.data),
};

/** Versioned WebSocket events (mirror lightrag/api/sampai/realtime/events.py). */
export type WsEvent =
  | { v: number; type: 'message_new'; message: GroupMessage }
  | { v: number; type: 'agent_typing'; thread_id: number; is_typing: boolean }
  | { v: number; type: 'typing'; thread_id: number; user_id: number; username: string; is_typing: boolean }
  | { v: number; type: 'presence'; thread_id: number; online_user_ids: number[] }
  | { v: number; type: 'read_receipt'; thread_id: number; user_id: number; last_seq: number }
  | { v: number; type: 'member_joined'; thread_id: number; user_id: number; username: string }
  | { v: number; type: 'member_left'; thread_id: number; user_id: number }
  | { v: number; type: 'invite_new'; invite: GroupInvite }
  | { v: number; type: 'invite_cancelled'; invite_id: number; group_chat_id: number }
  | { v: number; type: 'invite_accepted'; invite_id: number; group_chat_id: number; user_id: number }
  | { v: number; type: 'thread_unread_bump'; thread_id: number; unread_count: number }
  | { v: number; type: 'announcement_new'; announcement_id: number; classroom_id: number; author: string }
  | { v: number; type: 'comment_new'; announcement_id: number; classroom_id: number; author: string };

/** Build an authenticated WS URL (token from the in-memory cache, base from Config). */
export function wsUrl(path: string): string {
  const origin = Config.API_BASE.replace(/^http/, 'ws');
  const sep = path.includes('?') ? '&' : '?';
  return `${origin}${path}${sep}token=${encodeURIComponent(getToken() ?? '')}`;
}

// ── announcements ──
export interface AnnComment {
  id: number;
  announcement_id: number;
  created_by_id: number;
  content: string;
  created_at: string;
  author: UserSummary | null;
}
export interface Announcement {
  id: number;
  classroom_id: number;
  created_by_id: number;
  content: string; // sanitized HTML
  created_at: string;
  updated_at: string;
  author: UserSummary | null;
  comments: AnnComment[];
}

const AN = `${P}/announcements`;
export const announcementApi = {
  list: (cid: number): Promise<Announcement[]> => api.get(`${AN}/classrooms/${cid}`).then((r) => r.data),
  create: (cid: number, content: string): Promise<Announcement> =>
    api.post(`${AN}/classrooms/${cid}`, { content }).then((r) => r.data),
  remove: (id: number): Promise<void> => api.delete(`${AN}/${id}`).then(() => undefined),
  addComment: (id: number, content: string): Promise<AnnComment> =>
    api.post(`${AN}/${id}/comments`, { content }).then((r) => r.data),
  removeComment: (id: number, commentId: number): Promise<void> =>
    api.delete(`${AN}/${id}/comments/${commentId}`).then(() => undefined),
};

// ── folder (cross-file) quiz ──
export interface FolderQuizQuestionView {
  id: string;
  question: string;
  reasoning_type: string;
  hop_depth: number | null;
  source_file_names: string[];
  submitted: boolean;
  user_answer: string | null;
  reference_answer: string | null; // null until this question is submitted
  score: number | null; // 0–5
  missing: string[];
  incorrect: string[];
  verdict: string | null;
}
export interface FolderQuizFileInfo {
  file_id: number | null;
  filename: string;
  seed_count: number;
  reason: string;
}
export interface TopicScore {
  file_id: number | null;
  filename: string;
  mean_score: number; // 0–1
  question_count: number;
  correct_count: number;
}
export interface FolderQuizDetail {
  quiz_id: number;
  status: 'pending' | 'generating' | 'ready' | 'failed' | 'submitted';
  difficulty: string;
  difficulty_source: string;
  num_questions: number;
  error_msg: string | null;
  files: FolderQuizFileInfo[];
  diversity: Record<string, number>;
  warnings: string[];
  questions: FolderQuizQuestionView[];
  score: number | null;
  correct_count: number | null;
  total_count: number;
  graded_count: number;
  topic_scores: TopicScore[];
}
export interface SubmitQuestionResponse {
  question_id: string;
  score: number; // 0–5
  missing: string[];
  incorrect: string[];
  verdict: string;
  reference_answer: string;
  finished: boolean;
  aggregate_score: number | null;
  correct_count: number | null;
  graded_count: number;
  total_count: number;
}
export interface FolderQuizHistoryItem {
  quiz_id: number;
  difficulty: string;
  num_questions: number;
  status: string;
  score: number | null;
  graded_count: number;
  total_count: number;
  submitted_at: string | null;
  created_at: string;
  ready_at: string | null;
  n_files: number;
}
export interface FolderQuizHistoryResponse {
  items: FolderQuizHistoryItem[];
  has_open_quiz: boolean;
  open_quiz_id: number | null;
}

const FQ = `${P}/folder-quiz`;
export const folderQuizApi = {
  generate: (
    folderId: number,
    body: { difficulty?: 'easy' | 'medium' | 'hard'; file_ids?: number[] },
  ): Promise<{ quiz_id: number; status: string }> =>
    api.post(`${FQ}/folders/${folderId}/generate`, body).then((r) => r.data),
  get: (quizId: number): Promise<FolderQuizDetail> => api.get(`${FQ}/${quizId}`).then((r) => r.data),
  submitQuestion: (quizId: number, questionId: string, userAnswer: string): Promise<SubmitQuestionResponse> =>
    api.post(`${FQ}/${quizId}/questions/${questionId}/submit`, { user_answer: userAnswer }).then((r) => r.data),
  history: (folderId: number): Promise<FolderQuizHistoryResponse> =>
    api.get(`${FQ}/folders/${folderId}/history`).then((r) => r.data),
};

// ── error helpers (ported verbatim) ──
export function apiErrorDetail(err: unknown, fallback = 'Something went wrong'): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && (detail[0] as { msg?: string })?.msg)
    return String((detail[0] as { msg?: string }).msg);
  return fallback;
}

export function normalizeErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail.map((d: { msg?: string }) => d?.msg ?? JSON.stringify(d)).join('; ');
  return fallback;
}
