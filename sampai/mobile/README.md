# SAMpai Mobile (React Native / Expo)

React Native port of the SAMpai web app. Talks to the **unchanged** backend
(`lightrag/api/sampai`, port **9621**). Implementation plan: [`app-plan.md`](./app-plan.md).

Stack: Expo SDK 56 · Expo Router · NativeWind v4 · TanStack Query · Zustand · axios ·
`expo/fetch` (SSE chat) · native WebSocket (group chat).

## 1. Prerequisites

- Node 18+ (tested on 22) and **npm**.
- The SAMpai backend running and reachable on `:9621`
  (`sampai/docker/docker-compose.dev.yml` for the stores + `uvicorn` for the API).
- To run on **Android**: Android Studio + an emulator, or a physical device on the same Wi‑Fi.
- iOS requires a Mac or EAS cloud builds.

Because the app uses custom native modules (secure-store, reanimated, gesture-handler,
svg, bottom-sheet, build-properties), **Expo Go will not work** — you need a Dev Client.

## 2. Install

```bash
cd sampai/mobile
npm install
```

## 3. Configure the backend URL

The app reads `EXPO_PUBLIC_API_BASE` (see `.env.example`). Create `.env`:

```bash
cp .env.example .env
```

- **Android emulator** → `http://10.0.2.2:9621` (the default if unset).
- **iOS simulator** → `http://localhost:9621`.
- **Physical device** → `http://<your-LAN-IP>:9621` (run `ipconfig` on Windows to find the IPv4).
- **Production** → your Cloudflare Tunnel `https://…` URL.

Cleartext HTTP is already enabled for dev builds (`expo-build-properties`), so plain
`http://` works against the local backend.

## 4. Run (development)

Build + install the Dev Client once, then start Metro:

```bash
# Local native build (needs Android Studio/SDK):
npx expo run:android

# …or build a Dev Client in the cloud (needs an Expo account):
npx eas build --profile development --platform android   # then install the resulting APK
```

Subsequent runs just need Metro:

```bash
npx expo start --dev-client
```

Open the app → it loads the Dev Client and connects to Metro. Edit code → fast refresh.

## 5. Build (EAS)

```bash
npx eas login                                            # one-time
npx eas build --profile preview --platform android       # internal APK
npx eas build --profile production --platform android    # store AAB
npx eas build --profile production --platform ios        # iOS via EAS cloud (no Mac needed)
```

Set the production backend URL for standalone builds, e.g.:

```bash
EXPO_PUBLIC_API_BASE=https://<tunnel-domain> npx eas build --profile production --platform android
```

`eas.json` defines the `development` / `preview` / `production` profiles. App identifiers
(`com.sampai.mobile`) and the app name live in `app.json`.

## 6. Project structure

```
src/
  api/        client.ts (axios), sampai.ts (all endpoints + streamChat + wsUrl)
  lib/        token.ts (SecureStore cache), types.ts, utils, haptics, query-keys
  stores/     auth.ts, realtime.ts (user WS), theme.ts
  hooks/      use-group-chat-socket.ts (thread WS reducer)
  components/ ui/ primitives, error-boundary, file-status-badge
  features/   chat, quiz, flashcards, mindmap, group-chat, announcements
app/          Expo Router: (public) auth, (app) Stack -> (tabs) + classroom/folder/file/thread/folder-quiz
```

## 7. End-to-end verification checklist

With the backend up and the app on a device/emulator:

- [ ] Sign up → land on tabs → kill & reopen app → still signed in → log out.
- [ ] Create a classroom; join another by code; create a folder.
- [ ] Upload a PDF; watch status go pending → processing → ready; download it.
- [ ] Open the file → **Chat**: ask a question, see tokens stream in.
- [ ] **Quiz**: generate, take (MCQ + T/F), submit, review explanations.
- [ ] **Flashcards**: generate, flip, rate (Know/Unsure/Forgot).
- [ ] **Mindmap**: generate, expand nodes, ask about a node.
- [ ] Invite a second account; in **Threads** send messages, `@SAMpai` replies,
      typing/presence/read receipts update; accept the invite from **Alerts**.
- [ ] Classroom → **Announcements**: post (owner), comment; appears for the other user.
- [ ] Folder → **Cross-file quiz**: select files, generate, answer, see LLM grade + topic scores.
- [ ] Profile → toggle **Appearance** (System/Light/Dark) — theme switches live.

## Notes

- Push notifications are not wired yet (would need an additive backend `/auth/push-token`
  endpoint + `expo-notifications`).
- The backend is consumed as-is; only client config (`EXPO_PUBLIC_API_BASE`) changes per environment.
