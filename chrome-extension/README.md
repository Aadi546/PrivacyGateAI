# PrivacyGate Chrome extension

Created from the official WXT React starter. See the project's root README for Windows/macOS setup, pairing, security behavior, and verification instructions.

```sh
npm ci
npm run build
npm run compile
```

Load `.output/chrome-mv3` in desktop Chrome using **Load unpacked**. Keep the loopback backend running on port 8765. The side panel and service worker are generated through WXT entrypoints; do not hand-edit the generated manifest.
