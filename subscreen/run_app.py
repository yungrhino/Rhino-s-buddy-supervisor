"""Entry point of the desktop app (also what PyInstaller packages into Subscreen.exe)."""

import sys

from subscreen.app import main

if __name__ == "__main__":
    sys.exit(main())
