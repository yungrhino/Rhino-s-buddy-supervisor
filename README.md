# Rhino's Buddy Supervisor

Open-source (MIT) program for 3.5" USB secondary screens (Turing Smart Screen family): you decide what shows up on the little screen.

The editor speaks **English and Portuguese** (pick one the first time you open it; switch any time with the selector at the top of the page or in **System → Language**).

## Desktop app (recommended)

A program with a visual editor: live preview, **modules in slots** that you drag and resize, a **background image**, several pages,
port / rotation / brightness settings and **start with Windows**.

**Build the executable** (once, on Windows with Python installed): double-click `build_exe.bat`.
It creates `dist\RhinosBuddySupervisor\RhinosBuddySupervisor.exe` (and, if you want, a desktop shortcut).
Without building the `.exe`, `Start Rhinos Buddy Supervisor.bat` starts the same program straight from the source code.

- Opening the program shows the editor window; opening it again just brings forward the one that is already running.
- **System → Start with Windows** turns the screen on by itself at login, in the background (no window).
- Your settings live in `%APPDATA%\RhinosBuddySupervisor` (`layout.json`, `media\`, `rhinos_buddy.log`).
- The screen is redrawn with what you built; if the cable is unplugged it reconnects by itself.
- Security: the editor only listens on `127.0.0.1`, refuses other sites (Host / CSRF checks) and only accepts images.
- **Quit** button at the top of the page (and **System → Quit program**): asks for confirmation, then closes the program and stops updating the screen.

### Phone access (same Wi-Fi)

- **System → Phone access:** turn it on and scan the QR code with the phone camera. The phone opens the **same panel**, adapted to small screens, in its browser
  (Android and iOS, nothing to install). With **Also allow editing the panel from the phone** off (default) you only get the picture of the screen; the **View screen**
  / **Panel** buttons switch between the fullscreen picture (with Rotate and, on Android, Fullscreen) and the panel.
- **Pairing:** the QR code is valid for **5 minutes** (a countdown is shown) and works **once**; a new one appears right away. Scanning it gives that phone a session that lasts
  until the phone's browser is closed or you press **Disconnect** (the connected devices are listed on the PC). Turning phone access off, or closing the program, disconnects everyone.
- **Editing in sync:** changes made on the phone appear on the PC and on the screen and vice versa. If both save at once, the first save wins and the other side is refreshed.
  Not available from the phone: quitting, Windows start-up, restoring defaults and uploading images.
- Security: off by default; a separate tiny server on port 8766 (editor port + 1), bound **only to the PC's private network address**; the editor and its full API stay on `127.0.0.1`.
  Sessions are random 256-bit ids in a session cookie (HttpOnly, SameSite=Strict), kept in memory only; only private-network clients are served; the Host header is checked;
  changing calls need the editor's custom header; repeated wrong codes lock that address out for 5 minutes.
- Limits: the connection is plain HTTP on your local network (not encrypted), so someone on that network could in theory capture a session; whoever is connected sees the screen
  (including notifications, if any) and, if editing is on, can change the panel. Guest/"isolated" Wi-Fi blocks phone-to-PC traffic. Windows asks about the firewall the first time.
  There is no access from outside your home network, by design.

### Language

- The first time you open the program, a window asks you to choose **Português** or **English**. It only appears once.
- Switch later with the selector at the top of the page, or in **System → Language / Idioma**. The change is instant and covers the editor,
  module names, messages and the texts drawn on the screen (weekdays and months in the date card, alerts, "Nothing playing"...).
- In English, dates read "November 21, 2026" / "Sat, Nov 21", and numbers use a decimal point (the "decimal comma" option is Portuguese-only).
- Text you type yourself (labels, page names, free text) is never translated.
- Command-line output and the guide in `docs/` are still in Portuguese.

### What you can put on the screen

- **Number stability** (*Screen → Number stability*): every number that changes is redrawn piece by piece (the USB link is slow),
  so the default "Calm" ignores small fluctuations (CPU 3%→4%, ±1 °C, network ±50%). On an idle desk in a simulated test this dropped from
  ~2.8 to ~0.2 updates/s. "Real time" shows every reading. A number that really changes is still redrawn progressively: that is a hardware limit.
- **Radial indicators:** in **Appearance → Module indicator** choose horizontal bars or circles for all modules
  (CPU, GPU, VRAM, RAM, disk); each module can still have its own style in its options. There is also a "Radial" button at the top of the Modules tab and the **Rings** template (Template → Rings).
- **Music module:** shows what is playing (title and artist) and/or an audio visualizer (bars, mirrored, circular or beat pulse),
  freely sized on the grid. Each part can be switched on or off in the module options.
  It needs the optional packages in `requirements-extras.txt` (`build_exe.bat` tries to install them):
  `soundcard` captures what goes out of your speakers / headphones (any player) and `winrt-*` reads the current track from Windows.
  Without them Spotify is still read from its window title and the visualizer stays still, with a warning.
  In the module, "Now-playing appearance" has the **Expanded card** mode: album cover, title, artist and a progress bar with times
  (cover and times come from Windows and depend on the player reporting them; Spotify does).
  The **Audio visualizer** also exists as a separate card (group "Music" in the module list), spectrum only, without the track title.
  The visualizer follows the default Windows output device: when you connect Bluetooth headphones or switch speakers, the capture follows in about 1 second.
  Capture only runs while a visualizer is visible on the screen. Because of the slow USB link, the program limits the redraw
  rate by the size of the area: small slots (e.g. 2x1 cells) are smoother than large ones.
- **Notifications (WhatsApp Web, Discord, etc.):** off by default, because the text of an alert can be private.
  Turn it on in **Screen → Show Windows notifications on the screen**. Every card has **Show notification alerts on this card** (in its options): when an
  alert arrives, the card gives way to a panel with the app, title and message for a few seconds and then returns by itself to what it was
  showing (the visualizer keeps playing, for example). The **Notifications** module lists what is still in the Windows notification center
  (the alerts you have not opened), newest first; when an alert is opened or dismissed in Windows it leaves the list. Nothing leaves your computer.
  - Where they come from: the Windows notification center (needs the packages in `requirements-extras.txt` and
    *Settings → Privacy & security → Notifications → "Allow apps to access your notifications"*).
    For WhatsApp Web, turn on the site's notifications in the browser.
  - Without permission or packages, the program only uses the unread counter in the tab title (e.g. "(3) WhatsApp"), which only sees the
    visible tab and does not show who wrote. The status line in **Screen → Notifications** says which source is active, how many alerts are pending and, if something
    fails, why. If you grant the permission later, the program tries again by itself within 30 seconds.
  - The app filter also looks at the title and the text: WhatsApp Web arrives as "Google Chrome" or "Microsoft Edge",
    so "WhatsApp" in the filter works.
  - Use **Test alert** to see how it looks without waiting for a real message. You can also filter by app and
    hide the text (shows only "New notification").
  - The Notifications card is in the **Testing** category (see below) and may not work on every computer.
- **Light and dark mode:** button at the top of the editor (remembers your choice; the first time it follows the system theme).
- **"Testing" category:** in Modules → Add module, an expandable category gathers the cards that are still being tuned
  (for now, **Notifications (list)**). The Notifications card has text alignment (left, center, right).
- **Preview:** click outside a card to deselect it; resize by pulling any of the four corners.
- **Landscape ⇄ portrait:** when you rotate the screen, cards are rearranged without overlapping and each orientation remembers where each card was.
- **What's new:** the first time each version is opened, a pop-up shows the notes (tick "Do not show again" to stop it;
  System → What's new turns it on or off and shows it again).
- **Updating and uninstalling:** `Uninstall Rhinos Buddy Supervisor.bat` (in the program folder) closes the program, removes
  the automatic start and deletes the program folder; your data in `%APPDATA%\RhinosBuddySupervisor` is kept unless
  you choose "Desinstalar" and answer that you want it deleted too. To update: run the uninstaller (option 1) and extract the new zip.
  On the source code (no `.exe`) it only closes the program and removes the automatic start, without deleting the folder. Its prompts are in Portuguese.
- **"On this page" list** (Modules tab): shows everything on the screen, front to back. Click to
  select (even if a full-screen module covers the others), reorder with ▲▼ or use **Hide** to take
  a module off the screen without deleting it. Alt+click in the preview selects the module underneath.
- **Switch pages automatically:** the switch is in the "This page" card. When off, the screen always stays on the first page.

**Coming from the old name ("Subscreen")?** On first launch the program copies your settings and images from the old folder and switches the "Start with Windows" entry to the new one; nothing is deleted. After building the new `.exe` you can delete the old `dist\Subscreen` folder.

Command line (advanced): `python run_app.py [--background] [--no-hardware] [--port N]`.

---

# Command-line version

Open-source software (MIT) for 3.5" USB secondary screens (Turing Smart Screen family): **you decide what shows up on the little screen**.

Written from scratch in Python. No code, theme or image from the software that ships with the screen was copied.

## Installation

```
pip install -r requirements.txt
```

## Try it without the screen (simulator)

```
python -m rhinos_buddy run -c examples/config.toml --simulator --http 8080
```

Open http://127.0.0.1:8080 to see the screen live (or the `preview.png` file).

## Using the real screen

1. **Close the original `UsbMonitor.exe`** (only one program can open the COM port).
2. Find the port: `python -m rhinos_buddy ports` (Windows 10 needs no driver).
3. Edit `[device]` in `examples/config.toml` (`port = "COM5"`) and run:
   ```
   python -m rhinos_buddy run -c examples/config.toml
   ```

Standalone commands: `image photo.png`, `clear`, `brightness 40`, `hello`.

## What can go on the screen

| `type`       | What it does |
|--------------|--------------|
| `text`       | text with variables: `"CPU {cpu:.0f}%"`, `{ram}`, `{ram_used_gb}`, `{disk}`, `{net_down_kbs}`, `{net_up_kbs}`, `{cpu_temp}`, `{battery}`, `{now:%H:%M}` |
| `clock`      | time / date (`format` is strftime) |
| `bar`, `graph` | bar and graph of any metric |
| `image`      | PNG/JPG/animated GIF; if another program overwrites the file, the screen updates |
| `web_image`  | image from a URL every N seconds (camera, map, Grafana) |
| `command`    | runs **any command/script** and shows the output (text, or an image with `mode = "image"`) |
| `file`       | last lines of a text/log file |
| `http_json`  | a value from a JSON API |
| `plugin`     | your own Python with Pillow (see `examples/plugins/hello_plugin.py`) |
| `rect`       | cards / panels |

Several `[[page]]` blocks rotate by themselves (`duration`). Only the areas that changed are sent over USB, which keeps everything smooth.

## Hardware monitor (CPU/GPU, temperatures, RAM, network, date and time)

```
python -m rhinos_buddy run -c examples/config_pt.toml
```

(`config_pt.toml` is the Portuguese-language example; the text it draws can be edited freely.)

- **NVIDIA GPU:** usage and temperature through `nvidia-smi` (ships with the driver), nothing to install.
- **CPU temperature (and AMD/Intel GPU):** install [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor),
  open it **as administrator** and turn on *Options > Remote Web Server > Run* (port 8085).
- `python -m rhinos_buddy sensors` shows what was found. An unavailable sensor shows as `--`.
- Texts accept `{dia_semana}`, `{dia_semana_cap}`, `{mes}`, `{dia}`, `{ano}` (weekday, month, day, year in the interface language) and `decimal = ","`.

## Speed and "scanlines"

Measured on a real screen: **~128 KB/s fixed** (one full 480x320 frame = 2.4 s), the same for any
`baud` and `chunk_lines`. The "scanlines" are the frame itself being transferred. To reduce them:

1. Send fewer pixels: static background and only small dynamic areas (clock, bars, text).
2. GIFs/videos: use small areas (`w`/`h`) and `fit = "contain"`. Budget: ~64 thousand pixels/s
   (e.g. 120x120 at ~4 frames/s). The GIF plays in real time, dropping frames if the link cannot keep up.
3. Only the pixels that changed are sent (automatic).

`python -m rhinos_buddy bench` measures your screen's speed; `rotate` (portrait + software rotation) exists
but does not help on this hardware.

## Protocol (summary)

USB-CDC serial, 6-byte packets with packed 10-bit coordinates and the command in the last byte (`0xC5` = draw bitmap, followed by little-endian RGB565 pixels; `0x79` orientation; `0x6E` brightness). It lives in `rhinos_buddy/protocol.py` and is covered by tests.

## Status and limitations

- The protocol was validated on one real screen (Turing 3.5" Rev A, COM port, serial `USB35INCHIPSV2`). Other panel revisions may use slightly different protocols: if the image comes out skewed, with swapped colors or nothing shows, run `python -m rhinos_buddy ports` and `python -m rhinos_buddy hello` and open an issue with the output.
- CPU temperature only works where `psutil` exposes sensors (Linux). On Windows, use a `plugin` / `command` that reads LibreHardwareMonitor.

## Tests

```
pip install pytest && python -m pytest tests
```

## License, trademarks and privacy

- **License:** MIT (`LICENSE` file). Third-party libraries and the external programs mentioned are listed in
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md); the generated `.exe` ships with their full texts in `THIRD_PARTY_LICENSES.txt`.
- **Trademarks:** "Turing Smart Screen", "UsbMonitor", "Spotify", "Windows", "NVIDIA" etc. belong to their owners and are mentioned only to
  identify compatible products. The project is not affiliated with any of them.
- **Privacy:** everything runs on your computer. The editor only listens on `127.0.0.1` (the optional, off-by-default phone access listens on your private network address, see above); there is no telemetry, account or data upload. The only optional
  network connection is reading the local LibreHardwareMonitor (`127.0.0.1:8085`) and the URL widgets you configure yourself.
- **Publishing on GitHub and installing LibreHardwareMonitor:** see [`docs/GUIA_GIT_E_LICENCAS.md`](docs/GUIA_GIT_E_LICENCAS.md) (in Portuguese).
