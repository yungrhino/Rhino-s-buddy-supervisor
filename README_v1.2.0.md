# Rhino's Buddy Supervisor v1.2.0 — English language and quick exit

Open-source (MIT) replacement for the Turing Smart Screen 3.5" software: put anything you want on the secondary screen
(hardware stats, clock, music, notifications, images) with a visual editor in your browser.

## What's new

- **English language.** The first time you open the program, a window lets you choose **Português** or **English** (it appears only once,
  even if you had already turned off the "what's new" pop-up). You can switch at any time with the selector at the top of the page or in **System → Language**.
  The change is instant and covers:
  - the whole editor, module and option names, hints and messages;
  - the texts drawn on the screen itself: weekdays and months in the date card ("Saturday", "November 21, 2026"), the default labels,
    "Nothing playing", "No notifications" and notification alerts;
  - number format: English uses a decimal point (the "decimal comma" option is Portuguese-only).
- **Quit button** at the top of the page, next to the screen status. It asks for confirmation before closing the program, and
  **System → Quit program** now uses the same confirmation. The pop-up focuses **Cancel**, so pressing Enter never quits by accident; Esc cancels.
- **Documentation in English:** `README.md`, these release notes and the commit summaries are now written in English.

## Good to know

- Text you type yourself (labels, page names, free text) is never translated. The default first page is called "Principal" in layouts created before this
  version; the editor shows it as "Main" in English.
- Still in Portuguese: the command-line output, `Desinstalar Rhinos Buddy Supervisor.bat` prompts, `docs/GUIA_GIT_E_LICENCAS.md` and the notes of versions before 1.2.0.
- The English texts were written together with the code and have not been reviewed by a native speaker. If something reads oddly, please open an issue.

## How to update

1. In the folder of the old version, double-click **`Desinstalar Rhinos Buddy Supervisor.bat`** and choose **1 (Atualizar / Update)**. Your data (layout, images and settings in `%APPDATA%\RhinosBuddySupervisor`) is kept.
2. Download `RhinosBuddySupervisor-v1.2.0-windows.zip` below, extract it anywhere and open `RhinosBuddySupervisor.exe`.

Without the uninstaller (older versions): close the program, extract the zip over the old folder or into a new one and open the new executable; your data stays where it was.

## Requirements and notes

- Windows 10/11 and the Turing Smart Screen 3.5" (USB). CPU temperature needs LibreHardwareMonitor (guided install in `docs/GUIA_GIT_E_LICENCAS.md`, in Portuguese).
- The Notifications card is still in the **Testing** category: for it to read Windows, turn on *Settings → Privacy & security → Notifications → "Allow apps to access your notifications"*. Without the permission only the tab-title counter (e.g. "(3) WhatsApp") is used.
- The executable is not signed: Windows (SmartScreen) may show "unrecognized app". That is normal for new, independent programs.
- Features that depend on Windows (current track, notifications, audio capture, automatic start, the uninstaller) have not been run on a real PC; the automated tests cover their content and simulate the rest. If something behaves differently on yours, open an issue with the version (**System** tab) and what happened.

## License

MIT. Third-party libraries and their licenses ship with the program in `THIRD_PARTY_NOTICES.md` and `THIRD_PARTY_LICENSES.txt`.
