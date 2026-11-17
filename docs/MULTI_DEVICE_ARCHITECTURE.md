# EdgeMind â€” Multi-Device Architecture Specification

## 1. Executive Overview

When a user signs into Google Chrome with the same Google Account across multiple laptops (e.g., Laptop A and Laptop B), Chrome Sync automatically synchronizes browser extensions. However, **Chrome Sync does NOT and CANNOT install native machine executables, modify operating system registries, or synchronize local database volumes.**

This document defines the boundary between browser synchronization and local operating system configuration, and outlines the production multi-device architecture for EdgeMind.

---

## 2. Multi-Device Separation of Concerns

```
+--------------------------------------------------------------------------------------------------+
|                                    Chrome Sync Cloud Boundary                                    |
+--------------------------------------------------------------------------------------------------+
                                                 |
                 +-------------------------------+-------------------------------+
                 |                                                               |
                 v                                                               v
  +-----------------------------+                                 +-----------------------------+
  |          Laptop A           |                                 |          Laptop B           |
  |                             |                                 |                             |
  | [Chrome Web Store Sync]     |                                 | [Chrome Web Store Sync]     |
  |  - Extension code synced    |                                 |  - Extension code synced    |
  |  - Manifest V3 synced       |                                 |  - Manifest V3 synced       |
  |  - UI preferences synced    |                                 |  - UI preferences synced    |
  |                             |                                 |                             |
  | [OS Local Host Boundary]    |                                 | [OS Local Host Boundary]    |
  |  - edgemind_native_host.exe |                                 |  - MISSING until installed  |
  |  - HKCU Registry key        |                                 |  - MISSING until installed  |
  |  - Local PostgreSQL (5433)  |                                 |  - MISSING unless local DB  |
  |  - Local FastAPI (8000)     |                                 |  - MISSING unless local API |
  +-----------------------------+                                 +-----------------------------+
                 \                                                               /
                  \                                                             /
                   +-----------------------------+-----------------------------+
                                                 |
                                                 v
                               +-----------------------------------+
                               | Central Cloud Backend (Production)|
                               |  - Central FastAPI API Service    |
                               |  - Central PostgreSQL 16 (JSONB)  |
                               |  - Cloud User Authentication      |
                               |  - Cross-Device History Sync      |
                               +-----------------------------------+
```

---

## 3. Four-Layer Breakdown

### Layer 1: Chrome Web Store Extension Synchronization
- **Behavior:** Chrome Sync automatically propagates the extension from the Chrome Web Store to any browser instance where the user logs into their Google profile.
- **Synced Items:** HTML, CSS, client-side JS (`content.js`, `background.js`, `popup.js`, `extractor.js`), icons, and `chrome.storage.sync` key-values (such as UI theme preferences).
- **Not Synced:** Machine-specific binaries, OS files, or system permissions.

### Layer 2: Native Messaging Host Installation (Per-Machine)
- **Behavior:** Native Messaging requires:
  1. A physical binary on disk (e.g. `C:\Users\<user>\AppData\Local\EdgeMind\edgemind_native_host.exe`).
  2. A manifest JSON pointing to that path.
  3. A Windows Registry entry at `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host`.
- **Laptop B State:** When Laptop B syncs the extension, the extension will attempt to ping `com.edgemind.native_host`. Because the native host is absent on Laptop B, `chrome.runtime.sendNativeMessage` will return:
  ```text
  Specified native messaging host not found.
  ```
- **UX Solution:** The extension UI detects this status and displays an intuitive, non-blocking onboarding banner:
  > *"EdgeMind Extension detected on a new machine. Download and run the one-click EdgeMind Windows Installer to activate local background acceleration."*

### Layer 3: User Account Authentication
- **Behavior:** Authentication is decoupled from machine identity.
- **Flow:**
  - The developer logs into EdgeMind via email/password or OAuth (GitHub/Google).
  - The JWT access token and refresh token are stored in `chrome.storage.local` (or `chrome.storage.sync` with encrypted payload) on that specific device.
  - Revocation can occur per-session without invalidating sessions on other laptops.

### Layer 4: Cloud Project & Analysis-History Synchronization
- **Behavior:** Local PostgreSQL containers (`edgemind-postgres` on port 5433) are strictly isolated to the host machine. Analysis reports saved in Laptop A's Docker volume do not appear on Laptop B.
- **Production Solution:**
  - For developers working across multiple machines, the extension supports connecting to a central managed EdgeMind Cloud backend (`https://api.edgemind.dev`).
  - Analysis reports stored in native PostgreSQL 16 JSONB are indexed and retrieved using the user's account ID and project IDs.
  - When the developer views their analysis history on Laptop B, reports are fetched from the central API.

---

## 4. Supported Operational Modes

| Feature | Mode 1: Local Privacy / Offline | Mode 2: Multi-Device Cloud Sync |
| :--- | :--- | :--- |
| **Target Audience** | Single-device developers, offline work, sensitive enterprise codebases | Multi-laptop developers, distributed teams |
| **Analysis Engine** | Local FastAPI on `127.0.0.1:8000` | Cloud FastAPI on `https://api.edgemind.dev` |
| **Native Host** | Required for local process lifecycle management | Optional (not required if calling cloud endpoint) |
| **Database** | Host-bound PostgreSQL container (port 5433) | Managed PostgreSQL 16 Cloud Cluster with JSONB & GIN |
| **Cross-Device Sync** | None (data stays on local machine) | Real-time synchronization of reports and problem history |
| **Offline Support** | 100% functional without internet connection | Offline caching with sync upon reconnect |
