# CodeDoctor Chrome Extension

CodeDoctor is a Chrome Manifest V3 extension MVP that requests static analysis
of Python code from the local CodeDoctor API. Findings are heuristic and may
include false positives. Runtime execution is skipped.

## Folder layout

Place `manifest.json` and `README.md` directly in your existing
`extension/chrome/` folder. Keep your existing `popup/` and `scripts/` folders.

```text
extension/chrome/
├── manifest.json
├── README.md
├── popup/
│   ├── popup.html
│   ├── popup.css
│   └── popup.js
└── scripts/
    ├── content.js
    └── extractor.js
```

## Start the API

From the CodeDoctor project root, activate your virtual environment if needed,
then run:

```powershell
python -m uvicorn core.api:app --host 127.0.0.1 --port 8000
```

Keep the terminal open. Check `http://127.0.0.1:8000/health`.
Expected response:

```json
{"status":"healthy","service":"CodeDoctor"}
```

## Load the extension

1. Open Chrome and visit `chrome://extensions/`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select `extension/chrome/`, the folder containing `manifest.json`.
5. Pin CodeDoctor from Chrome's Extensions menu if desired.

## Test on LeetCode

1. Open a LeetCode problem page.
2. Select Python or Python3.
3. Click the CodeDoctor toolbar icon.
4. Confirm the API status is online.
5. Click **Analyze Code in Editor**.

Analysis should only happen after an explicit user action. The extension must not
submit or execute code.

## Troubleshooting

- **Manifest not found:** `manifest.json` must be directly inside
  `extension/chrome/`, not in `popup/` or `scripts/`.
- **API offline:** Start the API and check `/health`.
- **Extraction fails:** The editor may not expose a compatible Monaco model,
  may still be loading, or may have multiple candidate models. Do not analyze
  incomplete source.
- **Unsupported language:** This MVP supports Python only.
- **Source too large:** Maximum source size is 64 KiB.

## Privacy and security

- The user must explicitly request analysis.
- Source is sent to the local CodeDoctor API only.
- No cookie or browsing-history permissions are requested.
- The static-only API does not execute submitted code.
- Do not expose the local development API to untrusted networks. This MVP is
  not a production-hardened security boundary.
