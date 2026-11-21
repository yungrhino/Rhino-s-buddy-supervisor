"""Entry point of the desktop app (also what PyInstaller packages into RhinosBuddySupervisor.exe)."""

import sys

from rhinos_buddy.app import main

if __name__ == "__main__":
    sys.exit(main())
