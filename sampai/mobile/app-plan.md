# SAMpai Mobile App — React Native Implementation Plan

> **Scope:** The RN app lives in **`sampai/mobile/`**. The existing web app (`sampai/frontend/`), the LightRAG core (`lightrag/`), and the repo root are **not modified** except for the small, additive backend tweaks called out in Phase 0.

---

## 1. Context

SAMpai (*The Learning SAMpai*) is a feature-complete, AI-powered collaborative classroom platform. Teachers create classrooms, upload learning materials (PDF/DOCX/PPTX/TXT), and students learn through grounded AI features: per-file RAG chat, quizzes, flashcards (Leitner spaced repetition), interactive mind maps, real-time group chats with an `@SAMpai` agent, announcements, and cross-file quizzes.

- **Backend:** FastAPI graft inside LightRAG at `lightrag/api/sampai/` on port **9621**, routes prefixed `/api/sampai/...`. Stores: Postgres (app DB), Neo4j + Qdrant + Redis (LightRAG), Cloudflare R2 (files). Auth is **JWT Bearer** (no cookies). Realtime is **SSE** (chat streaming) + **two WebSockets** (user-level + per-thread).
- **Web frontend:** React 19 + Vite SPA at `sampai/frontend/` using Zustand, TanStack Query, axios, Tailwind v4, Radix UI, and a typed API layer (`src/api/sampai.ts`, `src/lib/types.ts`).

**Goal:** Build a React Native mobile app with full feature parity, **reusing the existing backend unchanged** and **reusing the web app's transport-agnostic data layer** (TypeScript types, axios client, API functions, Zustand stores, WS reducer). The mobile work is overwhelmingly a **UI re-implementation** — the API contract and ~80% of the data layer port directly.

> ⚠️ Source-of-truth note: the current system is `sampai/frontend/` + `lightrag/api/sampai/`. The repo also contains `The-Learning-SAMpai/` — an **old, abandoned** attempt (port 8000, ChromaDB, no `/api/sampai` prefix, no SSE). **Ignore it entirely.**

---

## 2. Locked Decisions

| Decision | Choice |
|---|---|
| RN foundation | **Expo SDK 52+ (managed) + Dev Client + EAS Build** |
| Platforms | **Android-first** (local dev on Windows), **iOS via EAS cloud** later |
| Visual fidelity | **Clean mobile-native redesign** — keep brand colors/theme + dark mode; bottom-tab nav; mindmap as collapsible/zoomable tree; lightweight native backgrounds (no WebGL) |
| Backend changes | **Minor additive tweaks allowed** (longer/refresh JWT, Expo-web CORS origin, push hooks). No changes to existing behavior. |
| Routing | **Expo Router** (file-based; maps cleanly to nested classroom/folder/file routes) |
| Language | TypeScript |

---

## 3. Target Architecture & Stack

| Concern | Web (current) | Mobile (RN) | Notes |
|---|---|---|---|
| Framework | React 19 + Vite | **Expo SDK 52+ + Dev Client** | EAS Build; `expo/fetch` is the key enabler for SSE |
| Routing | react-router-dom 7 | **Expo Router** (React Navigation under the hood) | Native stack + bottom tabs |
| Server state | TanStack Query 5 | **TanStack Query 5** | Reused as-is; `refetchInterval` for status polling |
| Client state | Zustand 5 | **Zustand 5** | Reused; persist via AsyncStorage adapter |
| HTTP | axios 1.7 | **axios 1.7** | Reused; interceptors ported |
| SSE (chat) | `fetch().body.getReader()` | **`expo/fetch`** (streaming) | RN core `fetch` can't stream; `expo/fetch` can. Fallback: `react-native-sse` (supports POST+body) |
| WebSocket | native `WebSocket` | **native `WebSocket`** | Identical API; token via `?token=` query param |
| Styling | Tailwind v4 | **NativeWind v4** | Reuse theme tokens (convert OKLCH→hex) |
| Token storage | `localStorage` | **expo-secure-store** + in-memory cache | Async store → sync cache for interceptors |
| Non-sensitive persist | localStorage | **@react-native-async-storage/async-storage** | Zustand persist, theme |
| File pick/upload | `<input type=file>` | **expo-document-picker** + RN `FormData` | Field name stays `'upload'` |
| File download | browser | **expo-file-system** / `Linking` | Presigned R2 URL (1h) |
| Markdown render | react-markdown | **react-native-markdown-display** | Chat + group messages |
| HTML render (announcements) | dangerouslySetInnerHTML | **react-native-render-html** | Content is sanitized server-side |
| Rich text authoring | TipTap | **lightweight formatting input** → limited HTML/markdown | Mobile-friendly composer |
| Icons | lucide-react | **lucide-react-native** | Same icon set |
| Toasts | sonner | **sonner-native** (or react-native-toast-message) | Same ergonomics |
| Gestures/anim | framer-motion / gsap | **react-native-reanimated** + **react-native-gesture-handler** | Flashcard swipe/flip, transitions |
| Bottom sheets | Radix Dialog | **@gorhom/bottom-sheet** | Invite, actions, pickers |
| Mindmap | @xyflow/react + dagre | **collapsible tree** (RN views) → optional **react-native-svg/Skia** graph | `dagre` is pure JS, reusable if graph view added |
| Backgrounds | OGL/WebGL | **expo-linear-gradient** + subtle Reanimated | Drop WebGL |
| Push (optional) | — | **expo-notifications** | Phase 8; needs backend token-register hook |
| UUID (idempotency) | crypto | **expo-crypto** / `uuid` | `client_msg_id` for optimistic sends |

---

## 4. Code Reuse Strategy (the core efficiency)

The web data layer is transport-agnostic TypeScript. **Copy/port these into `sampai/mobile/src/`:**

| Source (web) | Action | Adaptation needed |
|---|---|---|
| `sampai/frontend/src/lib/types.ts` | **Copy verbatim** | None (pure interfaces) |
| `sampai/frontend/src/api/sampai.ts` | **Port** (~538 lines) | Only `streamChat`, `wsUrl`, and `import.meta.env` refs; all `*Api` objects + `WsEvent` + error helpers reused as-is |
| `sampai/frontend/src/api/client.ts` | **Port** | Swap `localStorage`→token cache, `window.location`→logout event, `import.meta.env`→Config |
| `sampai/frontend/src/stores/auth.ts` | **Port** | Zustand persist → SecureStore/AsyncStorage |
| `sampai/frontend/src/stores/realtime.ts` | **Port** | User-level WS; uses ported `wsUrl` |
| `sampai/frontend/src/hooks/use-group-chat-socket.ts` | **Port** | Reducer is framework-agnostic; RN `WebSocket` API identical |
| `sampai/frontend/src/hooks/use-theme.ts` | **Port** | Persist via AsyncStorage |
| `sampai/frontend/src/index.css` (`:root`/`.dark` tokens) | **Convert** | OKLCH → hex/rgb into `tailwind.config.js` + JS theme object |
| Validation in `components/auth/auth-card.tsx` | **Reuse logic** | username `^[a-zA-Z0-9_-]{3,50}$`, password ≥8 + letter + number |

### Critical adaptations (highest-risk; build these first)

**(a) In-memory token cache** — interceptors/`streamChat`/`wsUrl` read the token synchronously, but SecureStore is async. Maintain a module-level cache hydrated on boot.
```ts
// src/lib/token.ts
let _token: string | null = null
export const getToken = () => _token
export const setToken = (t: string | null) => { _token = t }   // call on login/logout
export async function hydrateToken() {                          // call once at app start
  _token = await SecureStore.getItemAsync('token')
}
```

**(b) `client.ts` port** — only three lines change:
```ts
const api = axios.create({ baseURL: Config.API_BASE })          // was import.meta.env.VITE_API_BASE
api.interceptors.request.use((c) => { const t = getToken(); if (t) c.headers.Authorization = `Bearer ${t}`; return c })
api.interceptors.response.use(r => r, (e) => {
  if (e?.response?.status === 401) { setToken(null); authEvents.emit('logout') }  // was window.location = '/login'
  return Promise.reject(e)
})
```

**(c) SSE chat via `expo/fetch`** — the one place RN core fetch fails. The parsing loop from `sampai.ts:108-127` is reused verbatim:
```ts
import { fetch as expoFetch } from 'expo/fetch'
const res = await expoFetch(`${Config.API_BASE}/api/sampai/chat/files/${fileId}/ask`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken() ?? ''}` },
  body: JSON.stringify({ question }),
})
const reader = res.body!.getReader()       // expo/fetch supports streaming
// …identical `data:` line buffering + onToken(payload.token)…
```

**(d) `wsUrl` port** — derive ws origin from `Config.API_BASE`, token from cache:
```ts
export function wsUrl(path: string) {
  const origin = Config.API_BASE.replace(/^http/, 'ws')         // http→ws, https→wss
  const sep = path.includes('?') ? '&' : '?'
  return `${origin}${path}${sep}token=${encodeURIComponent(getToken() ?? '')}`
}
```

**(e) File upload (RN FormData)** — keep field name `'upload'`; build the RN file object from a picker URI:
```ts
const form = new FormData()
form.append('upload', { uri, name, type } as any)               // RN shape (not a File)
return api.post(`/api/sampai/files/upload/${folderId}`, form, { onUploadProgress })
```

---

## 5. Repository Layout (`sampai/mobile/`)

```
sampai/mobile/
├── app.config.ts            # Expo config; reads API_BASE from env; dev-client; android/ios
├── eas.json                 # EAS build profiles (development/preview/production)
├── tailwind.config.js       # NativeWind theme tokens (ported from index.css)
├── babel.config.js          # nativewind + reanimated plugins
├── metro.config.js          # nativewind
├── .env / app config        # API_BASE per environment
├── app/                     # Expo Router (file-based)
│   ├── _layout.tsx          # providers (Query, SafeArea, Gesture, Theme, Toast); auth gate; hydrateToken()
│   ├── (public)/            # landing, login, signup
│   ├── (app)/               # protected group
│   │   ├── _layout.tsx      # bottom tabs: Home / Threads / Notifications / Profile
│   │   ├── index.tsx        # Dashboard (classrooms)
│   │   ├── classroom/[id]/...           # classroom → folder → file (nested)
│   │   ├── threads/[id].tsx             # group chat thread
│   │   └── notifications.tsx
└── src/
    ├── config.ts            # Config.API_BASE (+ emulator/device defaults)
    ├── lib/                 # token.ts, types.ts (copied), utils, error-utils (copied)
    ├── api/                 # client.ts, sampai.ts (ported)
    ├── stores/              # auth.ts, realtime.ts, theme (ported)
    ├── hooks/               # use-group-chat-socket.ts (ported), query hooks
    ├── ui/                  # RN primitives: Button, Input, Card, Tabs/Segmented, Avatar, Badge, Progress, Sheet, Dialog
    └── features/            # auth, classrooms, files, chat, quiz, flashcards, mindmap, groupchat, announcements, folderquiz
```

---

## 6. Phase-by-Phase Plan

Each phase is independently runnable/demoable. Build the **risky transports first** (token cache → SSE → WS) so they're de-risked early.

### Phase 0 — Prereqs & minimal backend tweaks
- [ ] Confirm backend runs (`uvicorn` on `:9621`) + stores via `sampai/docker/docker-compose.dev.yml`.
- [ ] **Dev networking:** find host LAN IPv4 (`ipconfig`); Android emulator reaches host via **`10.0.2.2:9621`**, physical device via **`http://<LAN-IP>:9621`**. Enable cleartext HTTP for dev (Android `usesCleartextTraffic` / network-security-config; iOS ATS dev exception) in `app.config.ts`.
- [ ] **Backend tweaks (additive only)** in `lightrag/api/sampai/config.py` / env:
  - Raise `APP_JWT_EXPIRE_MIN` (e.g., 7 days) and/or add a `/auth/refresh` endpoint (optional) — mobile sessions shouldn't expire mid-use.
  - Add the Expo dev origin to `APP_CORS_ORIGINS` **only if** testing Expo **web** (native apps need no CORS).
  - (Deferred to Phase 8) optional `POST /auth/push-token` to register Expo push tokens.
- [ ] Verify reachability from the phone: `GET http://<LAN-IP>:9621/api/sampai/...` (health/login).

### Phase 1 — Scaffold & foundation
- [ ] `create-expo-app` (TS) in `sampai/mobile/`; add `expo-dev-client`; `eas init`; configure `eas.json` profiles.
- [ ] Install deps: NativeWind v4, reanimated, gesture-handler, expo-secure-store, async-storage, expo-document-picker, expo-file-system, expo-crypto, react-native-markdown-display, react-native-render-html, lucide-react-native, sonner-native, @gorhom/bottom-sheet, react-native-svg, @tanstack/react-query, zustand, axios.
- [ ] Configure NativeWind (babel/metro/tailwind.config) with **ported theme tokens** (convert `index.css` OKLCH → hex; light + dark).
- [ ] `src/config.ts` (API_BASE via `app.config.ts` extra + per-platform default).
- [ ] `_layout.tsx` providers: QueryClientProvider, SafeAreaProvider, GestureHandlerRootView, ThemeProvider, Toast host; call `hydrateToken()` on boot.
- [ ] Copy `types.ts`; port `client.ts` + `token.ts`; port `auth` store. **Build a few `ui/` primitives** (Button, Input, Card, Spinner).
- **Demo:** app boots, themed, can hit a health endpoint.

### Phase 2 — Auth & navigation shell
- [ ] Expo Router groups: `(public)` (landing/login/signup) vs `(app)` (protected). Auth gate redirects on missing/`logout` event (replaces `ProtectedRoute.tsx`).
- [ ] Login + Signup screens (reuse validation rules from `auth-card.tsx`; `authApi.login/signup/me`). On login: `setToken` + SecureStore + hydrate user; logout clears both.
- [ ] Bottom tabs: **Home (classrooms) / Threads / Notifications / Profile**.
- [ ] Wire 401→logout→redirect via `authEvents`.
- **Demo:** sign up, log in, persist session across restart, log out.

### Phase 3 — Classrooms, folders, files (browse + upload)
- [ ] Dashboard: joined vs created classrooms (`classroomApi.list`), create + join-by-code, leave/delete (`classroomApi`).
- [ ] Classroom screen: **Files** tab (folders → files) + **Announcements** + **Group Chats** tab entry (`folderApi`, `fileApi`, `announcementApi`).
- [ ] Folder screen: file list + cross-file quiz entry.
- [ ] **Upload:** expo-document-picker (pdf/docx/pptx/txt) → RN FormData (`'upload'`) → `fileApi.upload` with `onUploadProgress`.
- [ ] **Processing status polling:** TanStack Query `refetchInterval` (~2–3s) on `fileApi.status` until `completed`/`failed`; reflect `pending→processing→naive_ready→completed` (note: `naive_ready` unlocks chat/flashcards; `completed` unlocks quiz/mindmap).
- [ ] File download (presigned URL via `fileApi.download` → expo-file-system/Linking); delete (owner).
- **Demo:** create classroom, make folder, upload a PDF, watch it process, download it.

### Phase 4 — Per-file Chat (SSE) ← de-risks streaming
- [ ] File detail screen with a **segmented control** (Chat / Quiz / Flashcards / Mindmap).
- [ ] Chat: load history (`chatApi.history`), **stream answers** via the `expo/fetch` `streamChat` port, render markdown (react-native-markdown-display), show auto-summary first message, AbortController on unmount, clear history.
- **Demo:** ask a question on a processed file, watch tokens stream in.

### Phase 5 — Quiz + Flashcards
- [ ] **Quiz:** generate (`num_questions` 5/10/15, optional difficulty) → poll `quizApi.get` (~2s, 5-min stale) → take (MCQ radio / T-F toggle) → `submit` → review w/ explanations → history + resume open quiz (`has_open_quiz`).
- [ ] **Flashcards:** generate (10/20/30) → poll → **swipe/flip stack** (Reanimated + gesture-handler) → review `know|unsure|forgot` (Leitner box update) → due queue + box counts (`flashcardApi`).
- **Demo:** generate and complete a quiz; review a flashcard deck.

### Phase 6 — Mindmap (clean native tree)
- [ ] Generate (`mindmapApi.generate`, force option) → poll until `ready`.
- [ ] Render `tree_data` (`{version, root: MindNode}`) as a **collapsible, zoomable indented tree** (expand/collapse; lazy on `has_children`).
- [ ] Node tap → `mindmapApi.explore` (per-node summary) + per-node chat (`ask`, `chatHistory`) with `active_node_id` context.
- [ ] *(Optional stretch)* react-native-svg/Skia graph using `dagre` (pure JS) layout.
- **Demo:** generate a mindmap, expand nodes, chat about a node.

### Phase 7 — Group chat realtime (largest UI surface)
- [ ] Threads list (`groupChatApi.threads`): unread counts + previews.
- [ ] Thread screen: paginated messages (`messages(before_seq, limit)`), composer with **@mention autocomplete**, reply context, **optimistic send** with `client_msg_id` (expo-crypto UUID), markdown render.
- [ ] **Per-thread WebSocket:** port `use-group-chat-socket.ts` (reducer unchanged) over RN `WebSocket` via `wsUrl`; handle `message_new`, `typing`, `agent_typing`, `presence`, `read_receipt`, `member_joined/left`; reconnect w/ exponential backoff + **gap-fill refetch**; send typing + read receipts.
- [ ] **User-level WebSocket:** port `stores/realtime.ts` (`invite_new`, `invite_accepted`, `thread_unread_bump`, `announcement_new`, `comment_new`) → toasts + Notifications tab badge.
- [ ] Invite flow: `eligible-invitees` → `invite`; pending invites accept/reject/cancel.
- [ ] Respect rate limits (10 msgs/10s; agent 3/60s) → handle 429 with backoff.
- **Demo:** two accounts chat in real time; `@SAMpai` responds; typing/presence/read receipts work.

### Phase 8 — Announcements, cross-file quiz, notifications
- [ ] Announcements: list (render sanitized HTML via react-native-render-html), create (owner; simple formatting input → limited HTML/markdown), comments, delete; live updates via user socket.
- [ ] **Cross-file (folder) quiz:** file selection → `folderQuizApi.generate` → poll → **per-question submit** with LLM grade (0–5) + verdict/missing/incorrect → topic scores; history + resume.
- [ ] Notifications screen + tab badge (driven by user socket).
- [ ] *(Optional)* expo-notifications push: register token → backend `/auth/push-token` (Phase 0 hook) → server pushes on invite/mention.
- **Demo:** post an announcement (live to others); run a cross-file quiz; see notifications.

### Phase 9 — Theming & polish
- [ ] Dark/light toggle (ported `use-theme`), skeletons/spinners, error boundaries, toast errors via `apiErrorDetail`, pull-to-refresh, empty states, haptics, lightweight gradient backgrounds.

### Phase 10 — Build, test, ship
- [ ] EAS Build: Android (dev-client + internal APK/AAB); iOS via EAS. `expo-updates` for OTA.
- [ ] Device/emulator test matrix; LAN/Expo-tunnel for dev; production base URL (Cloudflare Tunnel from `sampai/docker`).
- [ ] Run the §9 end-to-end checklist; optional EAS Submit.

---

## 7. Cross-Cutting Concerns

- **Auth/session:** in-memory token cache (sync) backed by SecureStore (persist); `authEvents` decouples 401→logout from navigation; longer JWT (Phase 0) avoids mid-session expiry.
- **Realtime on mobile:** OS suspends sockets in background — rely on reconnect + gap-fill on foreground, and push (Phase 8) for background alerts. Keep the user-level socket alive app-wide (mirrors web `ProtectedRoute`).
- **Polling cadences (reuse web values):** file 2–3s, quiz 2s, flashcards 2s, mindmap 2s, pending chat ~1.5s — via TanStack Query `refetchInterval`.
- **Constraints to honor (client-side):** username `^[a-zA-Z0-9_-]{3,50}$`; password 8–72 + letter + number; quiz 5/10/15; cards 10/20/30; upload ≤100 MB; presigned URL 1h.
- **Networking matrix:** emulator `10.0.2.2:9621`; device `http://<LAN-IP>:9621`; prod `https://<tunnel-domain>` (auto `ws→wss` in `wsUrl`).

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| RN `fetch` can't stream SSE | **`expo/fetch`** (Phase 4 proves it early); fallback `react-native-sse` (POST+body supported) |
| Async SecureStore vs sync interceptor | In-memory token cache hydrated on boot |
| WS dies in background | Reconnect + gap-fill refetch; push notifications for background |
| 100 MB upload on mobile network | Progress UI + generous timeout + retry (backend takes single multipart; no chunking) |
| Mindmap graph perf/UX | Collapsible tree (chosen); Skia graph only as stretch |
| Rich-text authoring (TipTap) | Render HTML (sanitized) read-only; author via limited formatting/markdown |
| Cleartext HTTP blocked | Dev network-security-config / ATS exception; HTTPS via tunnel in prod |

---

## 9. Verification

**Run locally**
1. Backend + stores up (`sampai/docker/docker-compose.dev.yml`; API on `:9621`). Apply Phase 0 tweaks.
2. `cd sampai/mobile && npx expo start --dev-client` (install the dev client once via EAS/local). Set `API_BASE` to `10.0.2.2:9621` (emulator) or `http://<LAN-IP>:9621` (device).
3. Confirm phone/emulator reaches the API (login succeeds).

**End-to-end smoke checklist (maps to phases)**
- [ ] Sign up → log in → session survives app restart → log out (P2)
- [ ] Create classroom, join by code; create folder; upload PDF; status → completed; download (P3)
- [ ] Chat streams tokens on a processed file (P4)
- [ ] Generate/take/submit a quiz with review; generate + review flashcards (P5)
- [ ] Generate mindmap; expand nodes; node chat (P6)
- [ ] Two devices: real-time group chat, `@SAMpai` reply, typing/presence/read receipts, invites (P7)
- [ ] Post announcement (live to others); cross-file quiz per-question grading; notifications badge (P8)
- [ ] Dark/light toggle; error/empty/loading states (P9)
- [ ] EAS Android build installs and runs against prod base URL (P10)

---

## 10. Appendix — Backend API Contract (authoritative)

All routes prefixed `/api/sampai`. Auth: `Authorization: Bearer <jwt>` (WS uses `?token=`). Derived from `sampai/frontend/src/api/sampai.ts` + `lib/types.ts` (the source of truth).

- **auth:** `POST /auth/signup`, `POST /auth/login` → `{access_token, token_type, user}`, `GET /auth/me`
- **classrooms:** `GET /classrooms`, `GET /classrooms/:id`, `POST /classrooms`, `POST /classrooms/join/:code`, `POST /classrooms/:id/leave`, `DELETE /classrooms/:id`
- **folders:** `GET /folders/classroom/:cid`, `POST /folders/classroom/:cid`, `DELETE /folders/:id`
- **files:** `GET /files/folder/:fid`, `GET /files/:id`, `GET /files/:id/status`, `POST /files/upload/:fid` (multipart, field `upload`), `POST /files/:id/reprocess`, `GET /files/:id/download`, `DELETE /files/:id`
- **chat:** `GET /chat/files/:id/history`, `POST /chat/files/:id/ask` (**SSE** `data: {token}`), `DELETE /chat/files/:id/history`
- **flashcards:** `POST /flashcards/files/:id/generate`, `GET /flashcards/:deckId`, `GET /flashcards/files/:id/due`, `GET /flashcards/files/:id/history`, `POST /flashcards/cards/:cardId/review`
- **mindmap:** `POST /mindmap/files/:id/generate`, `GET /mindmap/files/:id`, `POST /mindmap/:mid/nodes/:nodeId/explore`, `GET /mindmap/:mid/chat`, `POST /mindmap/:mid/chat/ask`
- **quiz:** `POST /quiz/files/:id/generate`, `GET /quiz/:quizId`, `POST /quiz/:quizId/submit`, `GET /quiz/files/:id/history`
- **folder-quiz (cross-file):** `POST /folder-quiz/folders/:fid/generate`, `GET /folder-quiz/:quizId`, `POST /folder-quiz/:quizId/questions/:qid/submit`, `GET /folder-quiz/folders/:fid/history`
- **group-chat:** `GET /group-chat/threads`, `GET /group-chat/threads/:id`, `GET /group-chat/threads/:id/messages` (`before_seq`,`limit`), `POST /group-chat/threads/:id/messages`, `POST /group-chat/threads/:id/leave`, `POST /group-chat/threads/:id/read`, `GET /group-chat/files/:id/eligible-invitees`, `POST /group-chat/files/:id/invite`, `GET /group-chat/invites/pending`, `POST /group-chat/invites/:id/{accept,reject,cancel}`
- **announcements:** `GET /announcements/classrooms/:cid`, `POST /announcements/classrooms/:cid`, `DELETE /announcements/:id`, `POST /announcements/:id/comments`, `DELETE /announcements/:id/comments/:commentId`
- **WebSockets:** `GET /group-chat/ws/user?token=` (invites/announcements/unread), `GET /group-chat/ws/group-chat/:id?token=` (messages/typing/presence/read). Event union mirrors `WsEvent` in `sampai.ts`.
