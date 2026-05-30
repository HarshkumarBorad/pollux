# Aurora Desktop — Installation Guide

Cross-platform client for Aurora compute jobs and storage.

## System requirements

- OS: Windows 10 (1809+), macOS 11+, Ubuntu 22.04+ or equivalent.
- Memory: 4 GB RAM minimum, 8 GB recommended.
- Disk: 500 MB free.
- Network: HTTPS to `api.aurora.example` (port 443).

## Windows installation

1. Download `AuroraDesktop-Setup.exe` from `downloads.aurora.example`.
2. Right-click → **Run as administrator**.
3. Follow prompts; accept default install location (`C:\Program Files\Aurora`).
4. Launch from the Start menu.
5. Sign in with your Aurora account.

## macOS installation

1. Download `AuroraDesktop.dmg`.
2. Double-click to mount.
3. Drag Aurora Desktop into Applications.
4. Launch. macOS may prompt about an unidentified developer — open **System Settings → Privacy & Security** and click "Open Anyway".

## Linux installation

`.deb` for Debian/Ubuntu, `.rpm` for Fedora/RHEL:

```bash
# Debian / Ubuntu
sudo dpkg -i aurora-desktop_1.4.0_amd64.deb

# Fedora / RHEL
sudo rpm -i aurora-desktop-1.4.0.x86_64.rpm
```

A portable tarball is also available.

## Configuration

First launch prompts for:

1. Your Aurora API key (or interactive OAuth login).
2. Default project.
3. Telemetry preferences (toggleable in **Settings → Privacy** any time).

Config files:

- Windows: `%APPDATA%\Aurora\config.json`
- macOS: `~/Library/Application Support/Aurora/config.json`
- Linux: `~/.config/aurora/config.json`

## Troubleshooting

**"Cannot connect to api.aurora.example"** — check firewall, ensure HTTPS to `api.aurora.example:443` is allowed. Corporate proxies need configuration in **Settings → Network**.

**"API key invalid"** — generate a new key from the web console. Old keys are revoked when rotated; the desktop doesn't auto-pick-up rotated keys.

**Slow startup** — **Settings → Advanced → Clear cache**. Aurora Desktop will redownload metadata on next launch.

## Uninstall

- Windows: **Settings → Apps → Aurora Desktop → Uninstall**.
- macOS: drag from Applications to Trash; remove `~/Library/Application Support/Aurora` for a clean wipe.
- Linux: `sudo apt remove aurora-desktop` or equivalent.
