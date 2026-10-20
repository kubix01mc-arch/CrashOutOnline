# Crash Out

Crash Out is a card battler with a graphical desktop game and a browser game
that supports online multiplayer. The terminal-only game is not included.

## Play on your computer

Use Python 3.10 or newer. For the graphical desktop game, install its
dependencies and launch the window:

```powershell
python -m pip install -r requirements-windowed-online.txt
python play.py
```

To start the browser game on your computer or local Wi-Fi:

```powershell
python -m pip install -r requirements-browser.txt
python play.py browser
```

Open the local URL printed by the server. Players on the same Wi-Fi can use
the host computer's LAN URL. Keep the server running while playing.

## Play online across networks

Deploy the included `render.yaml` blueprint from this GitHub repository on
[Render](https://render.com/). See [BROWSER.md](BROWSER.md) for the full setup
and connection steps. After deployment, open the Render service URL in a
browser. Players can host or join a match using the six-digit room code.

The server keeps active rooms in memory, so use a single service instance.
Restarting or redeploying the service ends active matches. Free services may
sleep while idle and need time to wake before a new room can be created.

## Credits

See [`assets/ATTRIBUTION.txt`](assets/ATTRIBUTION.txt) for the required
attribution for the included bot icon.
