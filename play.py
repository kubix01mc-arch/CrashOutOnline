#!/usr/bin/env python3
"""Launch the Crash Out desktop window or browser game."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parent.parent
if str(PROJECTS_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECTS_DIR))


def main() -> None:
    mode = sys.argv[1].strip().lower() if len(sys.argv) > 1 else "window"
    if mode in ("window", "gui", "-w"):
        from crash_out_window import main as window_main

        window_main()
    elif mode in ("browser", "web", "wifi", "-b"):
        from crash_out_browser import main as browser_main

        browser_main()
    else:
        print(f"Unknown mode '{mode}'. Use: window | browser")
        sys.exit(1)


if __name__ == "__main__":
    main()
