#!/usr/bin/env python3
"""Launch Crash Out browser / LAN host (does not replace desktop play.py)."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

# Project root on sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    import uvicorn

    host_ip = lan_ip()
    port = 8765
    print()
    print("=" * 52)
    print("  CRASH OUT — Browser / WiFi Host")
    print("=" * 52)
    print()
    print(f"  On this PC:     http://127.0.0.1:{port}")
    print(f"  On same WiFi:   http://{host_ip}:{port}")
    print()
    print("  Create a room in the browser, share the room code.")
    print("  Desktop window/terminal modes are unchanged (play.py).")
    print()
    uvicorn.run("server.app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
