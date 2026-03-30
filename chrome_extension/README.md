# Pantheon COO — Chrome extension (MV3)

Run COO commands from any tab: popup, page context, and quick task list.

## Install (developer mode)

1. Open Chrome → **Extensions** → enable **Developer mode**.
2. Click **Load unpacked** and select this `chrome_extension/` folder.
3. Pin the extension. Set **API URL** (default `http://localhost:8002`) and paste your **JWT** from the web dashboard login (or use `AUTH_MODE=none` and leave token empty if your server allows it).

## Usage

- **Popup**: type a command → **Execute** (calls `POST /execute`).
- **Send page content to COO**: grabs visible text from the active tab into the command box.
- **Right-click** selected text → **Ask COO about selected text** (stores selection; open popup to refine/send).

## Notifications

When integrated with your workflow, the background worker can show **“Task done ✅”** via `chrome.notifications` (see `background.js`).

## Files

- `manifest.json` — MV3 manifest, host permissions for your API origin.
- `popup.html` / `popup.js` — UI and `execute()` fetch helper.
- `background.js` — service worker, context menu, notifications.
- `content.js` — extracts page text for the popup.
