# Elegoo Centauri Carbon - SDCP Control Skill

[![Agentskills](https://img.shields.io/badge/agentskills-3D%20Printer-blue)](https://www.agentskills.in/)

AI agent skill for controlling the **Elegoo Centauri Carbon** 3D printer via its native SDCP (Smart Device Control Protocol) WebSocket interface.

## Features

- 🌡️ Temperature monitoring & control (nozzle, bed, chamber)
- 📂 File management (list, details, rename)
- 🖨️ Print control (start, pause, resume, stop)
- 💨 Fan control (model, auxiliary, box fans)
- 💡 Light control
- 🎯 Axis jogging & homing
- ⚡ Print speed adjustment
- 📊 Print history
- 🖥️ Full CLI interface

## Setup

```bash
# Install dependency
pip install websockets

# Set printer IP (optional, can also pass to constructor)
export ELEGOO_PRINTER_IP="192.168.1.100"

# Or just use it
python references/elegoo_centauri.py status
```

## Compatible Printers

- Elegoo Centauri Carbon
- Other Elegoo printers using SDCP V3.0.0 protocol

## How It Works

This skill communicates with the printer via WebSocket on port 3030 using the SDCP protocol. The MainboardID is auto-discovered on first connection. No API keys or authentication required — the printer speaks SDCP natively.

## License

MIT
