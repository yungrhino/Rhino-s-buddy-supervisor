# Rhino's Buddy Supervisor v1.3.0 — Scrolling song titles

Open-source (MIT) replacement for the Turing Smart Screen 3.5" software: put anything you want on the secondary screen
(hardware stats, clock, music, notifications, images) with a visual editor in your browser.

## What's new

- **Scrolling titles in the music card.** A title (or artist) that is too wide for its area no longer gets cut with "…": it rests for about
  1.5 s, then scrolls past in a loop, like old MP3 players that had no room for the whole name. It restarts from the beginning on every new track.
  Short titles stay still. Turn it off with **Scroll long titles (like old MP3 players)** in the music module (on by default). It works in both the
  compact and the expanded (cover + progress) layouts.
- **More robust media detection (browser / YouTube).** Until now the program read only the session Windows calls "current", which can be a paused
  player or another tab while a browser is playing. It now checks **all** media sessions and uses the one that is actually playing. A failure while
  reading the track no longer hides it silently: it is written to the log (`%APPDATA%\RhinosBuddySupervisor`), and a problem in the progress smoothing falls back
  to showing the title without the progress bar.
- **Author link:** the GitHub profile (https://github.com/yungrhino) is shown next to the version at the top of the page and in the **System** tab.

## Good to know

- YouTube/browser detection could not be tested on a real Windows PC here; the change is covered by tests for the session choice and the fallbacks. If the track still does not show,
  please open an issue with the version and the log file.
- Scrolling redraws only the text line, about 8 times per second, so it stays well inside the USB budget.

## How to update

1. In the folder of the old version, double-click **`Uninstall Rhinos Buddy Supervisor.bat`** (named `Desinstalar Rhinos Buddy Supervisor.bat` in versions up to 1.2.0) and choose **1 (Update)**. Your data (layout, images and settings in `%APPDATA%\RhinosBuddySupervisor`) is kept.
2. Download `RhinosBuddySupervisor-v1.3.0-windows.zip` below, extract it anywhere and open `RhinosBuddySupervisor.exe`. From 1.2.1 on, opening a newer version automatically replaces a copy that is still running.

## Requirements and notes

- Windows 10/11 and the Turing Smart Screen 3.5" (USB). CPU temperature needs LibreHardwareMonitor (guided install in `docs/GUIA_GIT_E_LICENCAS.md`, in Portuguese).
- The Notifications card is still in the **Testing** category.
- The executable is not signed: Windows (SmartScreen) may show "unrecognized app". That is normal for new, independent programs.

## License

MIT. Third-party libraries and their licenses ship with the program in `THIRD_PARTY_NOTICES.md` and `THIRD_PARTY_LICENSES.txt`.
