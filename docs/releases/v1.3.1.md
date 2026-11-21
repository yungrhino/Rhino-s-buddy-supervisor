# Rhino's Buddy Supervisor v1.3.1 — All artists on screen

Open-source (MIT) replacement for the Turing Smart Screen 3.5" software: put anything you want on the secondary screen
(hardware stats, clock, music, notifications, images) with a visual editor in your browser.

## What's new

- **Fix: only the first artist was shown for Spotify tracks.** Spotify reports just the first artist to the Windows media session, while its
  window title lists all of them. The program now reads the Spotify window title once per track and, when it describes the same track and
  extends the artist given by Windows, uses the complete list (e.g. "kouth, Cashley, Necroez, SYMSESH"). A long list scrolls like a long title
  (option **Scroll long titles**).

## Good to know

- This relies on the Spotify **desktop app** window title. If Spotify itself does not put every artist there, the card keeps showing what Windows reports.
  It could not be tried against a real Spotify here; the merging rule is covered by tests. If it does not work for you, open an issue with the version and the track.
- Other players (browser, YouTube, …) are unchanged: they show the artist/channel their media session reports.

## How to update

1. In the folder of the old version, double-click **`Uninstall Rhinos Buddy Supervisor.bat`** and choose **1 (Update)**. Your data (`%APPDATA%\RhinosBuddySupervisor`) is kept.
2. Download `RhinosBuddySupervisor-v1.3.1-windows.zip` below, extract it anywhere and open `RhinosBuddySupervisor.exe`. A copy of 1.2.1 or newer that is still running is replaced automatically.

## License

MIT. Third-party libraries and their licenses ship with the program in `THIRD_PARTY_NOTICES.md` and `THIRD_PARTY_LICENSES.txt`.
