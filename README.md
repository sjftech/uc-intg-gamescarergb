# Games Care RGB Switch — Unfolded Circle Remote 3 Integration

An integration driver for the [Unfolded Circle Remote 3](https://www.unfoldedcircle.com/) that exposes a select entity for switching inputs on a [Games Care RGB Switch](https://www.gamescare.eu/).

Supports up to 4 boards (32 ports) via extension boards. Each input port can be given a custom name during setup.

## Features

- Select entity with named inputs for clean, readable switching
- Supports 1–4 boards (8, 16, 24, or 32 ports)
- Custom port names set during setup (e.g. "PS2", "GameCube", "SNES")
- Reconfigure at any time to rename ports
- Runs directly on the UCR3 remote — no external server needed

---

## Installation

### Step 1 — Download the latest release

Go to the [Releases](../../releases/latest) page and download `uc-intg-gamescarergb-*-aarch64.tar.gz`.

### Step 2 — Upload to the Remote

1. Open your remote's web interface at `http://your-remote-ip`
2. Go to **Integrations** → **Add new** → **Install custom**
3. Select the downloaded `uc-intg-gamescarergb-*-aarch64.tar.gz` file
4. Wait for the upload to complete

### Step 3 — Setup

1. The integration will appear in your integrations list — click it and select **Start setup**
2. Enter the **IP address or hostname** of your switch (e.g. `192.168.1.100`)
3. Give it a friendly **name** (e.g. `Living Room Switch`)
4. Enter the number of **extension boards** (0 for a single 8-port board)
5. On the next screen, name each of your inputs (e.g. "PS2", "GameCube", "SNES")
6. Click **Finish** — the select entity will appear ready to use

### Reconfiguring

To rename inputs, go to the integration in your remote's settings and select **Reconfigure**. Your existing names will be pre-filled.

---

## Notes

- The switch communicates over plain **HTTP** on port 80 — no SSL
- Port 0 is the **Auto** mode (no forced input) — you can rename this to anything (e.g. "Off")
- The remote tracks the active input in memory; it resets to Auto if the integration restarts
