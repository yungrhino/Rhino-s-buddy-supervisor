# Rhino's Buddy Supervisor v1.7.0 — Storage card and easier pairing

Open-source (MIT) replacement for the Turing Smart Screen 3.5" software: put anything you want on the secondary screen
(hardware stats, clock, music, notifications, images, disk usage) with a visual editor in your browser.

## What's new

- **Storage card.** Disk usage as a card for one drive or a list of all drives. Everything is optional: which drive, used %, used / total, free space, temperature
  (LibreHardwareMonitor), read / write speed, bar or ring, and whether removable drives are listed.
- **Short pairing code and link under the QR.** Besides the QR code, the panel shows an 8-character code (`ABCD-2345`), the address to type it into and the full link with **Copy link** / **Copy code**,
  for phones that cannot scan. The same short code is inside the QR, which makes the QR smaller and easier to read. Same rules: 5 minutes, single use, lock-out after repeated wrong tries.
- **Phone screen view.** The picture turns automatically to the orientation where it is biggest (portrait and landscape layouts both fill the phone). **Rotate: auto / off / on**.
  Fullscreen locks the orientation to the picture's shape where the browser allows it (Android); iPhone Safari has no page fullscreen.
- **What's new history.** *System → What's new* lists every earlier version and opens its notes.
- **CI / Windows.** The phone server no longer sets `SO_REUSEADDR` on Windows (it let a second program share the port); the workflow runs pytest with `-rfE --tb=short` and `PYTHONUTF8=1`.

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
