# EdgeMind â€” Windows Authenticode Signing Strategy for Production

## 1. Executive Summary & Current Status

- **Binary Target:** `scripts\edgemind_native_host.exe` (Chrome Native Messaging Host for Windows)
- **Current Signature Status:** **Unsigned**
- **Windows Security Impact:**
  On Windows 11 (22H2 and later), Microsoft **Smart App Control (SAC)** evaluates newly introduced executables using AI and the cloud-backed Microsoft Intelligent Security Graph (ISG). Unsigned executables or executables lacking established reputation are blocked with:
  ```text
  [WinError 4551] The operation was blocked by Smart App Control
  (ERROR_ACCESS_DISABLED_BY_POLICY / 0x800711C7)
  ```
- **Guiding Constraint:** Windows security mechanisms (Smart App Control, Windows Defender, Memory Integrity) must **never** be disabled, downgraded, or bypassed.

---

## 2. Production Code Signing Architecture

To achieve frictionless production distribution across corporate and consumer Windows workstations, `edgemind_native_host.exe` must be digitally signed with a trusted **Authenticode** certificate recognized by the Microsoft Root Certificate Program.

```
+-----------------------------------------------------------------------+
|                            CI/CD Pipeline                             |
|                                                                       |
|  1. Compile C# Source                                                |
|     csc.exe /target:exe /out:edgemind_native_host.exe ...            |
|                           |                                           |
|                           v                                           |
|  2. Sign with Authenticode + RFC 3161 Timestamp                       |
|     Azure Trusted Signing (or EV HSM Code Signing)                   |
|                           |                                           |
|                           v                                           |
|  3. Verify Authenticode Signature                                    |
|     signtool verify /pa /v edgemind_native_host.exe                  |
+---------------------------+-------------------------------------------+
                            |
                            v
+-----------------------------------------------------------------------+
|                        Target Windows 11 Client                       |
|                                                                       |
|  1. Chrome initiates Native Messaging launch                          |
|  2. Windows kernel / Smart App Control inspects binary                |
|  3. Valid CA Chain verified via Windows Trusted Root Store            |
|  4. Counter-signature verified via RFC 3161 Timestamp                 |
|  5. Smart App Control allows execution without security prompts       |
+-----------------------------------------------------------------------+
```

---

## 3. Recommended Signing Providers

### Option A: Azure Trusted Signing (Recommended for Cloud CI/CD)
- **Provider:** Microsoft Azure Trusted Signing (formerly Azure Code Signing / ACS).
- **Security:** Private keys reside in Microsoft FIPS 140-2 Level 3 managed HSMs; no physical USB tokens required.
- **Identity Verification:** Microsoft identity validation for organizations.
- **Cost:** Subscription-based (significantly lower operational overhead than physical token management).
- **Reputation:** Native immediate trust with Windows SmartScreen and Smart App Control.

### Option B: Extended Validation (EV) Code Signing Certificate
- **Providers:** DigiCert, Sectigo, GlobalSign.
- **Security:** Requires hardware token (YubiKey / Safenet eToken) or Cloud HSM (e.g., DigiCert ONE / AWS CloudHSM).
- **Reputation:** Instant SmartScreen reputation without warm-up periods.

---

## 4. CI/CD Automated Signing Workflow

### Step 1: Compilation
```powershell
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe `
    /nologo `
    /target:exe `
    /optimize+ `
    /out:scripts\edgemind_native_host.exe `
    scripts\edgemind_native_host.cs
```

### Step 2: Sign with Authenticode & RFC 3161 Timestamp
Using `signtool.exe` with an RFC 3161 timestamping authority:
```powershell
signtool.exe sign `
    /fd SHA256 `
    /tr "http://timestamp.digicert.com" `
    /td SHA256 `
    /d "EdgeMind Native Messaging Host" `
    /du "https://edgemind.dev" `
    /sha1 <CERTIFICATE_THUMBPRINT> `
    scripts\edgemind_native_host.exe
```

*Note on Timestamping:* An RFC 3161 timestamp is **mandatory**. It ensures the executable remains valid and trusted even after the certificate itself expires, as long as it was signed during the certificate's validity window.

### Step 3: Verification Script
```powershell
# Verify signature via Windows API
$sig = Get-AuthenticodeSignature -FilePath scripts\edgemind_native_host.exe
if ($sig.Status -ne "Valid") {
    Write-Error "Authenticode validation failed: $($sig.StatusMessage)"
    exit 1
}
Write-Host "Authenticode Signature Verified: $($sig.SignerCertificate.Subject)"
```

---

## 5. Development vs. Production Policy

| Dimension | Local Development (Current) | Production Distribution |
| :--- | :--- | :--- |
| **Binary State** | Unsigned | Authenticode Signed (SHA-256) |
| **Timestamp** | None | RFC 3161 Secure Timestamp |
| **Smart App Control** | Tests gracefully skip native host invocation (`WinError 4551`) while pure Python protocol tests run 100% | Allowed immediately by policy |
| **Chrome Web Store** | Extension tested against local unpacked host | Extension published on Store, paired with signed native installer |
