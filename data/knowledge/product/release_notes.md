# Aurora Desktop — Release Notes

## v1.4.0 — 2026-04-15

### New
- **Multi-project switcher** — quickly jump between projects from the title bar.
- **Job templates** — save commonly-used compute job configurations as named templates.
- **Dark mode** — toggle via **Settings → Appearance**, or follow system.

### Improved
- Faster cold start: 2.1s → 0.9s on a typical Windows machine.
- Memory usage during long-running job monitoring reduced by ~35%.
- Error messages from the API now include suggested fixes where possible.

### Fixed
- Crash when uploading files larger than 4 GB on Windows. (#2841)
- Settings panel no longer flickers when switching themes. (#2867)
- Job logs no longer truncate at 64 KB — full logs are streamed and displayed live.

## v1.3.2 — 2026-02-20

### Fixed
- **Security:** patched an issue in the OAuth callback handler. CVE-2026-0042. **All users should upgrade.**
- Auth token refresh failed after machine sleep on macOS. (#2755)

## v1.3.1 — 2026-01-30

### Fixed
- Storage downloads occasionally hung indefinitely on slow networks. (#2701)
- "Open in Terminal" did nothing on Linux. (#2710)

## v1.3.0 — 2025-12-12

### New
- Storage browser with drag-and-drop upload.
- Live tail for running compute jobs.
- Keyboard shortcuts: `Ctrl/Cmd + K` opens the command palette.

### Removed
- Legacy v0 API support — please migrate to v1. Endpoints under `/v0` now return `410 Gone`.
