# Pantheon COO OS — Mobile (Expo)

React Native app for Pantheon COO OS: login, run commands, browse tasks, voice input, and settings.

## Prerequisites

- Node.js 18+
- [Expo CLI](https://docs.expo.dev/get-started/installation/) (`npx expo` works without global install)
- iOS Simulator (Mac) or Android emulator / physical device

## Install

```bash
cd mobile_app
npm install
```

## Run

```bash
npx expo start
```

Then press `i` (iOS), `a` (Android), or scan the QR code with Expo Go.

## API URL

Default API is `http://localhost:8002`. On a **physical device**, `localhost` refers to the phone — use your computer’s LAN IP (e.g. `http://192.168.1.10:8002`).

Change it in **Settings → API URL → Save**.

## Auth

- **Login** uses `POST /auth/login` and stores the JWT in **AsyncStorage** (`coo_token`).
- Backend should use `AUTH_MODE=jwt` for authenticated flows, or `AUTH_MODE=none` for open local testing (token optional).

## Voice

**Voice** tab records audio and calls `POST /voice/transcribe?auto_execute=true` (requires `OPENAI_API_KEY` on the server).

## Project layout

- `App.tsx` — navigation (stack + bottom tabs)
- `services/api.ts` — HTTP client (`execute`, `listTasks`, etc.)
- `screens/` — Login, Dashboard, Task detail, Voice, Settings
