# EdgeMind VS Code Extension

EdgeMind is an AI-powered static code analysis, code hygiene, and adaptive test intelligence platform.
This extension brings EdgeMind's static analysis, diagnostic reporting, and edge-case test generation directly into Visual Studio Code.

---

## Prerequisites

- **Node.js**: v18.0.0 or later (v20+ recommended)
- **npm**: v9.0.0 or later
- **Visual Studio Code**: v1.85.0 or later
- **EdgeMind Backend**: Running locally on `http://127.0.0.1:8000` (or remote URL)

---

## Getting Started & Building

1. Navigate to the extension directory:
   ```bash
   cd extension/vscode
   ```

2. Install local development dependencies:
   ```bash
   npm install
   ```

3. Compile TypeScript:
   ```bash
   npm run compile
   ```
   Or run the watcher during development:
   ```bash
   npm run watch
   ```

4. Run unit tests:
   ```bash
   npm test
   ```

---

## Running in Development

1. Open `extension/vscode` in Visual Studio Code (or open the root repository).
2. Press `F5` (or go to **Run and Debug** -> **Run Extension**).
3. A new **Extension Development Host** window will open with the EdgeMind extension loaded.
4. The Status Bar in the bottom right will display:
   - `$(circle-filled) EdgeMind: Online` when the backend is reachable.
   - `$(circle-outline) EdgeMind: Offline` when the backend is unreachable.
5. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS) to open the Command Palette.
6. Execute available commands:
   - `EdgeMind: Hello` — Displays a confirmation message confirming EdgeMind is running.
   - `EdgeMind: Show Output Channel` — Opens the **EdgeMind** Output Channel.
   - `EdgeMind: Check Backend Status` — Performs an immediate health check (`GET /health`) with progress feedback.

---

## Available Commands

| Command | Identifier | Description |
| :--- | :--- | :--- |
| **EdgeMind: Hello** | `edgemind.hello` | Displays an information notification confirming the extension is active. |
| **EdgeMind: Show Output Channel** | `edgemind.showOutput` | Reveals the EdgeMind output panel in VS Code. |
| **EdgeMind: Check Backend Status** | `edgemind.checkBackend` | Queries `GET /health` on the configured backend URL and updates status. |

---

## Configuration Settings

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `edgemind.backendUrl` | `string` | `http://127.0.0.1:8000` | Base URL of the EdgeMind FastAPI backend service. |

---

## Project Structure

```
extension/vscode/
├── .vscode/
│   ├── launch.json          # Debug launch configuration for Extension Development Host
│   └── tasks.json           # Build tasks (npm compile / watch)
├── src/
│   ├── extension.ts         # Extension entry point & command registration
│   ├── api/
│   │   ├── client.ts        # Reusable HTTP client with timeout & error handling
│   │   └── endpoints.ts     # Backend API endpoint paths
│   ├── types/
│   │   └── api.ts           # Typed API schemas matching core/schemas.py
│   ├── ui/
│   │   └── statusBar.ts     # Status Bar item manager (Online/Offline)
│   ├── utils/
│   │   ├── configuration.ts # VS Code configuration reader
│   │   ├── logger.ts        # OutputChannel logger utility
│   │   └── urlValidator.ts  # URL validation & normalization helper
│   └── test/
│       └── apiClient.test.ts # Self-contained Node unit tests for ApiClient
├── package.json             # Extension manifest & command contributions
├── tsconfig.json            # TypeScript configuration
└── README.md                # Extension documentation
```

---

## Development Roadmap

- [x] **Phase A**: Extension Skeleton & Core Commands
- [x] **Phase B**: API Client & Health Connectivity
- [ ] **Phase C**: Active File Static Analysis
- [ ] **Phase D**: Selected Code Snippet Analysis
- [ ] **Phase E**: Diagnostics Provider & QuickFix Actions
- [ ] **Phase F**: Interactive Results Webview Panel
- [ ] **Phase G**: Adaptive Test Generation & CodeLens
- [ ] **Phase H**: Configuration & SecretStorage Authentication
- [ ] **Phase I**: Verification & Marketplace Packaging
