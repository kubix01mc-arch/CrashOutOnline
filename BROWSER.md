# Crash Out — Online Multiplayer

The Tkinter window has **Host Online** and **Join by 6-digit Code** buttons. Online
matches use the existing WebSocket game server in this repository.
Browser matches use the same eleven special-card effects and turn-status rules
as the windowed game.

## Run on macOS

Install Python 3.10 or newer with Tcl/Tk support (the official macOS installer
from [python.org](https://www.python.org/downloads/macos/) includes Tkinter).
In Terminal, change to the project folder and install the online dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-windowed-online.txt
```

Launch the graphical game with `python play.py window`, or run
`python play.py browser` to start the browser/LAN server. For browser mode, open
the local URL printed in Terminal. The graphical game's online buttons open the
online match in the default browser on macOS; the LAN server stays running until
you close the game window. Keep Terminal and the game window open while hosting.
If macOS asks, allow incoming network connections for Python to host LAN games.

## Deploy the public server (once)

Cross-Wi-Fi play requires a public server; a room code alone cannot connect
computers on different networks. This project includes a Render blueprint in
`render.yaml`.

1. Push this project to a GitHub repository and create a Render account.
2. In Render, create a new Blueprint Instance from that repository.
3. Wait for the service to deploy, then copy its `https://...onrender.com` URL.
4. On each computer, install the windowed multiplayer dependencies:

```bash
python -m pip install -r requirements-windowed-online.txt
```

5. In the game window choose **Host Online** or **Join by 6-digit Code**. On first
	use, enter the deployed server URL. It is saved on that computer.
6. The host creates a room in the online window and shares the six-digit code.
	Friends choose **Join by 6-digit Code** and enter that code.

Keep the Render service to one instance: room state is held in memory and is not
shared between multiple server instances. Restarting or redeploying the service
ends active rooms. Render's free service may sleep when idle; allow it to wake
before creating a room.

## Host on the same Wi-Fi

Install `requirements-windowed-online.txt` as above. The host chooses **Host on
LAN**; the window starts a local server and displays its LAN address. Friends on
that same Wi-Fi choose **Join LAN by Code**, enter the host address, then enter
the six-digit code shown in the lobby. The host must leave the game window open
for the room to stay online. Allow the game through Windows Firewall on private
networks if prompted.

## Local browser mode

For local testing or same-Wi-Fi games, install `requirements-browser.txt` and run
`python play.py browser`. Cross-Wi-Fi players must use the deployed server URL,
not a host computer's `127.0.0.1` or LAN address.
