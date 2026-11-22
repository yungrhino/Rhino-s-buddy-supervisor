# Rhino's Buddy Supervisor v1.5.0 — Stable repository checks

Open-source (MIT) replacement for the Turing Smart Screen 3.5" software: put anything you want on the secondary screen
(hardware stats, clock, music, notifications, images) with a visual editor in your browser.

## What's new

- **Fix: the GitHub Actions checks failed after updating from the zip.** Extracting a new zip over the old folder never deletes files, so a repository could end up with
  the old uninstaller (`Desinstalar Rhinos Buddy Supervisor.bat`, which keeps the old name of the application on purpose to clean up old installs) and older `README_v*.md` files next to the new ones.
  Two repository checks (`test_app_identity_is_renamed` and `test_release_readme_matches_the_current_version`) treated those leftovers as errors.
  They now accept an uninstaller under any name and older release notes, and still fail on a real leftover of the old application name or on missing/newer release notes.
  A regression test covers this.
- **The program itself did not change** from 1.4.0 (phone view, confirmed working on a real iPhone).

## Good to know

- After extracting a new zip over an old checkout, you can delete the old files that no longer exist in the new zip (`Desinstalar Rhinos Buddy Supervisor.bat`,
  `Iniciar Rhinos Buddy Supervisor.bat`, older `README_v*.md`) before committing, to keep the repository tidy. It is no longer required for the checks to pass.

## How to update

1. In the folder of the old version, double-click **`Uninstall Rhinos Buddy Supervisor.bat`** (named `Desinstalar Rhinos Buddy Supervisor.bat` in versions up to 1.2.0) and choose **1 (Update)**. Your data (`%APPDATA%\RhinosBuddySupervisor`) is kept.
2. Download `RhinosBuddySupervisor-v1.5.0-windows.zip` below, extract it anywhere and open `RhinosBuddySupervisor.exe`.

## License

MIT. Third-party libraries and their licenses ship with the program in `THIRD_PARTY_NOTICES.md` and `THIRD_PARTY_LICENSES.txt`.
