# Rhino's Buddy Supervisor v1.7.1 — Windows connection fix

Open-source (MIT) replacement for the Turing Smart Screen 3.5" software: put anything you want on the secondary screen
(hardware stats, clock, music, notifications, images, disk usage) with a visual editor in your browser.

## What's new

- **Windows connection fix.** Both local servers (editor and phone) now close each connection gracefully (FIN, then wait for the client to finish reading). Before, Windows could reset the connection while a reply was in flight (WinError 10053), which made 3 tests fail on GitHub Actions with Python 3.11.
- Everything from 1.7.0 (storage card, short pairing code, auto-rotating phone view, what's-new history) is unchanged.

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
