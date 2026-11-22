# Rhino's Buddy Supervisor v1.6.0 — Phone panel and volume

Open-source (MIT) replacement for the Turing Smart Screen 3.5" software: put anything you want on the secondary screen
(hardware stats, clock, music, notifications, images) with a visual editor in your browser.

## What's new

- **The full panel on your phone.** In **System → Phone access**, turn it on and scan the QR code. The phone opens the same panel as the desktop, laid out for small screens
  (single column: preview first, the Modules / Appearance / Screen / System panel below), and talks to the PC: what you change shows up on the PC panel and on the screen, and the other way round.
  Two switches: **Allow phone access** (view only: the picture of the screen, with **Rotate** and, on Android, **Fullscreen**) and **Also allow editing the panel from the phone** (off by default).
  The **View screen** and **Panel** buttons move between the two.
- **Safer pairing instead of a fixed link.** The QR code now holds a **one-time pairing code valid for 5 minutes**, with a countdown next to it; once it is used (or expires) a new one appears.
  Scanning it gives the phone a **session** that lasts until the browser is closed or you press **Disconnect** (**Disconnect all** too) in the list of connected devices on the PC.
  Turning phone access off or closing the program ends every session. Sessions are never written to disk. The fixed link of 1.4.x is gone.
- **Editing without clashes.** Every saved layout gets a revision number. If the PC and the phone save at the same time, the first one wins and the other editor is refreshed with a notice; otherwise each side
  picks up the other's change within about 2 seconds.
- **Music card: PC volume (%).** New option **Show the PC volume (%) in the corner**: a speaker icon with the percentage (or "Muted") in a corner of the first line that is reserved for it, so the scrolling title
  keeps its own window and never runs into it. Off by default; left out automatically when the card is too narrow.

## Security design

- Off by default. A **separate server** (editor port + 1), bound to the PC's **private network address only**; the desktop editor and its full API stay on `127.0.0.1`.
- Pairing code (128 bits, 5 minutes, single use) → session id (256 bits) in a **session cookie** (HttpOnly, SameSite=Strict, no expiry date).
- Viewing and editing are separate switches. With editing on, only an **allow-list** works: read the state, save the layout, change page focus, read already-uploaded images. **Not** available from the phone: quit,
  Windows start-up, restore defaults, reconnect, language, uploads and the phone-access controls themselves.
- Only private-network clients are served; the Host header must be one of this PC's addresses; changing calls need the editor's custom header on top of SameSite=Strict; unknown sessions and wrong codes lock the address out for 5 minutes after 8 tries.
- The state sent to the phone has no folder paths.

## Good to know

- The connection is **plain HTTP** on your local network, not encrypted: someone who can capture traffic on that network could take over a session, and a connected phone sees the screen (including notifications, if a notification card is showing)
  and, with editing on, can change the panel. Turn phone access off when you do not need it. There is no access from outside your home network, on purpose. Guest or "client-isolated" Wi-Fi blocks phone-to-PC traffic; Windows may ask about the firewall (allow **private networks**).
- Touch dragging/resizing of cards works through the same pointer events as the mouse, but the layout is tuned for options-based editing first; if dragging feels off on your phone, please open an issue with the phone model.
- The volume is read from the Windows default output device through the Core Audio interface; it was written without a real Windows PC to try it. If the percentage never appears, open an issue with the version and the log (`%APPDATA%\RhinosBuddySupervisor`).
- Tested here with an emulated phone browser, a real HTTP client against the server (pairing, expiry, single use, sessions, allow-list, conflicts, lock-out) and by decoding the generated QR code.

## How to update

1. In the folder of the old version, double-click **`Uninstall Rhinos Buddy Supervisor.bat`** (named `Desinstalar Rhinos Buddy Supervisor.bat` in versions up to 1.2.0) and choose **1 (Update)**. Your data (`%APPDATA%\RhinosBuddySupervisor`) is kept.
2. Download `RhinosBuddySupervisor-v1.6.0-windows.zip` below, extract it anywhere and open `RhinosBuddySupervisor.exe`. A copy of 1.2.1 or newer that is still running is replaced automatically.
3. If you used phone access in 1.4.x, scan the new QR code once: old fixed links stop working.

## License

MIT. Third-party libraries and their licenses ship with the program in `THIRD_PARTY_NOTICES.md` and `THIRD_PARTY_LICENSES.txt`.
