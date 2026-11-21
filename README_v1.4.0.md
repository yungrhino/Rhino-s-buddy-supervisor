# Rhino's Buddy Supervisor v1.4.0 — Phone view with QR code

Open-source (MIT) replacement for the Turing Smart Screen 3.5" software: put anything you want on the secondary screen
(hardware stats, clock, music, notifications, images) with a visual editor in your browser.

## What's new

- **See the screen on your phone (same Wi-Fi).** Open **System → Phone access**, turn on **Allow viewing the screen on a phone** and scan the QR code with the
  phone camera. The phone's browser shows the same picture as the Buddy screen, as large as it fits (about 8 updates per second). Works on Android and iOS,
  nothing to install. Two buttons: **Rotate** (fills a phone held upright; remembered) and **Fullscreen** (Android browsers; iOS Safari does not offer page fullscreen).
  The phone keeps its screen awake while the page is open, where the browser allows it.
- **Link controls on the PC:** a **Copy link** button and **Generate new link**, which replaces the secret and makes the old QR/link stop working immediately.
  While it is on, a "📱 Phone on" tag appears at the top of the editor.
- Built-in QR code generator (no extra package).

## Security design

Phone access is the only part of the program that listens beyond your own computer, so it is deliberately small:

- **Off by default.** Nothing is reachable from the network until you turn it on (your choice is remembered across restarts).
- **A separate server** on port 8766 (editor port + 1), bound to the PC's **private network address only** — never to every interface. It serves two things: the
  viewer page and the current picture. The editor and its API (layout, uploads, quit...) stay on `127.0.0.1` and cannot be reached from the network.
- **Secret token** (128 bits) required on every request, compared in constant time. Replaceable at any time.
- **Only private-network clients** (10.x, 172.16–31.x, 192.168.x, link-local) are served, so even a router forwarding the port to the internet gets nothing;
  the Host header must be one of this PC's own addresses; the server is **read-only** (GET only); **8 wrong tokens in a minute lock that address out for 5 minutes**.
- Tight response headers (CSP, no-store, no-referrer, no framing); the viewer page loads nothing from outside.

## Good to know

- The connection is **plain HTTP** on your local network, not encrypted: anyone on that network who has the link can see the screen, including notifications if a
  notification card is showing. Do not share the link or the QR code, and turn it off when you do not need it. There is no access from outside your home network, on purpose.
- Guest or "client-isolated" Wi-Fi networks block traffic between phone and PC. Windows may ask about the firewall the first time (allow **private networks**).
- Editing from the phone is not part of this version.
- This could not be tried on a real phone and Windows firewall here; it was tested with an emulated phone browser, a real HTTP client against the server (security rules,
  lock-out, read-only, token change) and by decoding the generated QR code. If something behaves differently on your network, open an issue with the version and what happened.

## How to update

1. In the folder of the old version, double-click **`Uninstall Rhinos Buddy Supervisor.bat`** (named `Desinstalar Rhinos Buddy Supervisor.bat` in versions up to 1.2.0) and choose **1 (Update)**. Your data (`%APPDATA%\RhinosBuddySupervisor`) is kept.
2. Download `RhinosBuddySupervisor-v1.4.0-windows.zip` below, extract it anywhere and open `RhinosBuddySupervisor.exe`. A copy of 1.2.1 or newer that is still running is replaced automatically.

## License

MIT. Third-party libraries and their licenses ship with the program in `THIRD_PARTY_NOTICES.md` and `THIRD_PARTY_LICENSES.txt`.
