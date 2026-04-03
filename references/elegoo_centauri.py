#!/usr/bin/env python3
"""
Elegoo Centauri Carbon - SDCP WebSocket Client
Complete control library for the Elegoo Centauri Carbon 3D printer.

Usage:
    from elegoo_centauri import ElegooCentauri
    
    async with ElegooCentauri(ip="192.168.1.100") as printer:
        status = await printer.get_status()
"""

import json
import uuid
import time
import asyncio
import websockets
import os

# ── Configuration ─────────────────────────────────────────
# Set your printer IP here or via environment variable
PRINTER_IP = os.environ.get("ELEGOO_PRINTER_IP", "192.168.1.100")
WS_PORT = int(os.environ.get("ELEGOO_WS_PORT", "3030"))
MAINBOARD_ID = os.environ.get("ELEGOO_MAINBOARD_ID", "")  # Auto-discovered if empty
# ──────────────────────────────────────────────────────────

WS_URL = f"ws://{PRINTER_IP}:{WS_PORT}/websocket"

# SDCP Commands
CMD = {
    "GET_PRINTER_STATUS": 0,
    "GET_PRINTER_ATTR": 1,
    "SEND_PRINTER_DISCONNECT": 64,
    "SEND_PRINTER_START_PRINT": 128,
    "SEND_PRINTER_SUSPEND_PRINT": 129,
    "SEND_PRINTER_STOP_PRINT": 130,
    "SEND_PRINTER_RESTORE_PRINT": 131,
    "GET_BLACKOUT_STATUS": 134,
    "SEND_BLACKOUT_ACTION": 135,
    "SEND_PRINTER_EDIT_NAME": 192,
    "EDIT_PRINTER_FILE_NAME": 193,
    "GET_PRINTER_FILE_LIST": 258,
    "GET_PRINTER_FILE_DETAIL": 260,
    "GET_PRINTER_HISTORY_ID": 320,
    "GET_PRINTER_TASK_DETAIL": 321,
    "DELETE_PRINTER_HISTORY": 322,
    "GET_PRINTER_HISTORY_VIDEO": 323,
    "EDIT_PRINTER_VIDEO_STREAMING": 386,
    "EDIT_PRINTER_TIME_LAPSE_STATUS": 387,
    "EDIT_PRINTER_AXIS_NUMBER": 401,
    "EDIT_PRINTER_AXIS_ZERO": 402,
    "EDIT_PRINTER_STATUS_DATA": 403,
}


def make_message(cmd, mainboard_id, data=None):
    """Build an SDCP protocol message."""
    return json.dumps({
        "Id": "",
        "Data": {
            "Cmd": cmd,
            "Data": data or {},
            "RequestID": uuid.uuid4().hex,
            "MainboardID": mainboard_id,
            "TimeStamp": int(time.time()),
            "From": 1
        }
    })


class ElegooCentauri:
    """Async client for Elegoo Centauri Carbon via SDCP WebSocket."""
    
    def __init__(self, ip=PRINTER_IP, port=WS_PORT, mainboard_id=MAINBOARD_ID):
        self.ip = ip
        self.port = port
        self.ws_url = f"ws://{ip}:{port}/websocket"
        self.mainboard_id = mainboard_id
        self._ws = None
        self._status = {}
        self._attributes = {}
    
    async def __aenter__(self):
        self._ws = await websockets.connect(self.ws_url, open_timeout=10)
        # Auto-discover MainboardID if not set
        if not self.mainboard_id:
            await self._send_no_wait(CMD["GET_PRINTER_STATUS"])
            msgs = await self._drain_messages(4)
            # The MainboardID can be extracted from response topics
            if msgs["status"]:
                topic = msgs["status"][0].get("Topic", "")
                if "/" in topic:
                    self.mainboard_id = topic.split("/")[-1]
        return self
    
    async def __aexit__(self, *args):
        if self._ws:
            await self._ws.close()
            self._ws = None
    
    async def _send(self, cmd, data=None, timeout=5):
        """Send a command and wait for the first matching response."""
        msg = make_message(cmd, self.mainboard_id, data)
        await self._ws.send(msg)
        
        # Wait for response
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                response = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
                data = json.loads(response)
                
                # Check if this is a status update
                topic = data.get("Topic", "")
                if f"sdcp/status/" in topic:
                    self._status = data.get("Status", self._status)
                    continue
                if f"sdcp/attributes/" in topic:
                    self._attributes = data.get("Attributes", self._attributes)
                    continue
                
                # Return response messages
                cmd_resp = data.get("Data", {}).get("Cmd")
                if cmd_resp == cmd:
                    return data
                # Also return if it's a direct response (Ack field present)
                if "Ack" in data.get("Data", {}).get("Data", {}):
                    return data
            except asyncio.TimeoutError:
                break
        return None
    
    async def _send_no_wait(self, cmd, data=None):
        """Send a command without waiting for response."""
        msg = make_message(cmd, self.mainboard_id, data)
        await self._ws.send(msg)
    
    async def _drain_messages(self, duration=3):
        """Read all pending messages for a duration."""
        results = {"status": [], "attributes": [], "responses": []}
        deadline = time.time() + duration
        while time.time() < deadline:
            try:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                response = await asyncio.wait_for(self._ws.recv(), timeout=min(remaining, 1))
                data = json.loads(response)
                topic = data.get("Topic", "")
                if "sdcp/status/" in topic:
                    self._status = data.get("Status", self._status)
                    results["status"].append(data)
                elif "sdcp/attributes/" in topic:
                    self._attributes = data.get("Attributes", self._attributes)
                    results["attributes"].append(data)
                else:
                    results["responses"].append(data)
            except asyncio.TimeoutError:
                break
        return results
    
    # ── Status & Info ──────────────────────────────────────
    
    async def get_status(self):
        """Get current printer status (temps, fans, lights, print info)."""
        await self._send_no_wait(CMD["GET_PRINTER_STATUS"])
        msgs = await self._drain_messages(4)
        return self._status
    
    async def get_attributes(self):
        """Get printer attributes (name, firmware, capabilities, etc.)."""
        await self._send_no_wait(CMD["GET_PRINTER_ATTR"])
        msgs = await self._drain_messages(4)
        return self._attributes
    
    async def get_full_info(self):
        """Get both status and attributes."""
        await self._send_no_wait(CMD["GET_PRINTER_STATUS"])
        await self._send_no_wait(CMD["GET_PRINTER_ATTR"])
        msgs = await self._drain_messages(5)
        return {
            "status": self._status,
            "attributes": self._attributes,
        }
    
    # ── Temperature Control ────────────────────────────────
    
    async def set_nozzle_temp(self, temp):
        """Set nozzle target temperature in °C."""
        return await self._send(CMD["EDIT_PRINTER_STATUS_DATA"], {"TempTargetNozzle": int(temp)})
    
    async def set_bed_temp(self, temp):
        """Set heated bed target temperature in °C."""
        return await self._send(CMD["EDIT_PRINTER_STATUS_DATA"], {"TempTargetHotbed": int(temp)})
    
    async def set_chamber_temp(self, temp):
        """Set chamber target temperature in °C."""
        return await self._send(CMD["EDIT_PRINTER_STATUS_DATA"], {"TempTargetBox": int(temp)})
    
    # ── Fan Control ────────────────────────────────────────
    
    async def set_fan_speed(self, fan_type, speed):
        """
        Set fan speed. fan_type: 'ModelFan', 'AuxiliaryFan', or 'BoxFan'. speed: 0-100.
        Note: ALL fan values must be sent together.
        """
        # Get current fan speeds first
        if not self._status:
            await self.get_status()
        
        current = dict(self._status.get("CurrentFanSpeed", {"ModelFan": 0, "AuxiliaryFan": 0, "BoxFan": 0}))
        current[fan_type] = max(0, min(100, int(speed)))
        
        return await self._send(CMD["EDIT_PRINTER_STATUS_DATA"], {"TargetFanSpeed": current})
    
    async def set_all_fans(self, model=0, auxiliary=0, box=0):
        """Set all fan speeds at once. Values 0-100."""
        return await self._send(CMD["EDIT_PRINTER_STATUS_DATA"], {
            "TargetFanSpeed": {
                "ModelFan": max(0, min(100, int(model))),
                "AuxiliaryFan": max(0, min(100, int(auxiliary))),
                "BoxFan": max(0, min(100, int(box))),
            }
        })
    
    # ── Light Control ──────────────────────────────────────
    
    async def set_light(self, on=True):
        """Turn the printer light on or off."""
        if not self._status:
            await self.get_status()
        current = dict(self._status.get("LightStatus", {"SecondLight": 0, "RgbLight": [0, 0, 0]}))
        current["SecondLight"] = 1 if on else 0
        return await self._send(CMD["EDIT_PRINTER_STATUS_DATA"], {"LightStatus": current})
    
    # ── Print Control ──────────────────────────────────────
    
    async def start_print(self, filepath):
        """Start printing a file. filepath should be like '/local/model.gcode'."""
        return await self._send(CMD["SEND_PRINTER_START_PRINT"], {"FileName": filepath})
    
    async def pause_print(self):
        """Pause the current print."""
        return await self._send(CMD["SEND_PRINTER_SUSPEND_PRINT"])
    
    async def resume_print(self):
        """Resume a paused print."""
        return await self._send(CMD["SEND_PRINTER_RESTORE_PRINT"])
    
    async def stop_print(self):
        """Stop/cancel the current print."""
        return await self._send(CMD["SEND_PRINTER_STOP_PRINT"])
    
    async def set_print_speed(self, percentage):
        """Set print speed percentage (e.g., 100, 150, 50)."""
        return await self._send(CMD["EDIT_PRINTER_STATUS_DATA"], {"PrintSpeedPct": int(percentage)})
    
    # ── Axis Movement ──────────────────────────────────────
    
    async def jog_axis(self, axis, distance):
        """Jog an axis by distance (mm). axis: 'X', 'Y', 'Z'. distance can be negative."""
        return await self._send(CMD["EDIT_PRINTER_AXIS_NUMBER"], {"Axis": axis.upper(), "Distance": float(distance)})
    
    async def home_axes(self, axes=None):
        """Home axes. axes: list like ['X', 'Y', 'Z'] or None for all."""
        if axes is None:
            axes = ["X", "Y", "Z"]
        return await self._send(CMD["EDIT_PRINTER_AXIS_ZERO"], {"AxisList": [a.upper() for a in axes]})
    
    # ── File Management ────────────────────────────────────
    
    async def get_file_list(self, path="/local"):
        """List files on the printer."""
        resp = await self._send(CMD["GET_PRINTER_FILE_LIST"], {"Url": path}, timeout=5)
        if resp and "Data" in resp and "Data" in resp["Data"]:
            return resp["Data"]["Data"].get("FileList", [])
        return []
    
    async def get_file_detail(self, filepath):
        """Get details/thumbnail for a specific file."""
        resp = await self._send(CMD["GET_PRINTER_FILE_DETAIL"], {"Url": filepath})
        if resp and "Data" in resp and "Data" in resp["Data"]:
            return resp["Data"]["Data"].get("FileInfo", {})
        return {}
    
    async def rename_file(self, old_path, new_path):
        """Rename a file on the printer."""
        return await self._send(CMD["EDIT_PRINTER_FILE_NAME"], {"SrcPath": old_path, "TargetPath": new_path})
    
    # ── Print History ──────────────────────────────────────
    
    async def get_print_history(self):
        """Get print history."""
        resp = await self._send(CMD["GET_PRINTER_HISTORY_ID"], timeout=5)
        if resp and "Data" in resp and "Data" in resp["Data"]:
            return resp["Data"]["Data"].get("HistoryData", [])
        return []
    
    async def get_task_detail(self, task_id):
        """Get details for a specific print task."""
        resp = await self._send(CMD["GET_PRINTER_TASK_DETAIL"], {"Id": [task_id]})
        if resp and "Data" in resp and "Data" in resp["Data"]:
            return resp["Data"]["Data"].get("HistoryDetailList", [])
        return []
    
    async def delete_history(self, task_id):
        """Delete a print history entry."""
        return await self._send(CMD["DELETE_PRINTER_HISTORY"], {"Id": [task_id]})
    
    # ── Disconnect ─────────────────────────────────────────
    
    async def disconnect(self):
        """Send disconnect command to printer."""
        return await self._send(CMD["SEND_PRINTER_DISCONNECT"])


# ── CLI Interface ──────────────────────────────────────────

async def cli_main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: elegoo_centauri.py <command> [args...]")
        print("\nEnvironment variables:")
        print("  ELEGOO_PRINTER_IP   - Printer IP address (default: 192.168.1.100)")
        print("  ELEGOO_WS_PORT      - WebSocket port (default: 3030)")
        print("  ELEGOO_MAINBOARD_ID - Mainboard ID (auto-discovered if empty)")
        print("\nCommands:")
        print("  status              - Get current printer status")
        print("  info                - Get printer attributes")
        print("  files               - List files on printer")
        print("  files <path>        - List files at path")
        print("  start <filepath>    - Start printing a file")
        print("  pause               - Pause current print")
        print("  resume              - Resume paused print")
        print("  stop                - Stop current print")
        print("  nozzle <temp>       - Set nozzle temperature")
        print("  bed <temp>          - Set bed temperature")
        print("  chamber <temp>      - Set chamber temperature")
        print("  fan <type> <speed>  - Set fan speed (ModelFan/AuxiliaryFan/BoxFan, 0-100)")
        print("  light <on|off>      - Toggle light")
        print("  jog <axis> <dist>   - Jog axis (X/Y/Z, distance in mm)")
        print("  home [axes...]      - Home axes (default: all)")
        print("  speed <pct>         - Set print speed percentage")
        print("  history             - Get print history")
        return
    
    command = sys.argv[1].lower()
    
    async with ElegooCentauri() as printer:
        if command == "status":
            status = await printer.get_status()
            print(json.dumps(status, indent=2))
            
        elif command == "info":
            attrs = await printer.get_attributes()
            print(json.dumps(attrs, indent=2))
            
        elif command == "files":
            path = sys.argv[2] if len(sys.argv) > 2 else "/local"
            files = await printer.get_file_list(path)
            for f in files:
                size_mb = f.get("FileSize", 0) / (1024 * 1024)
                name = f.get("name", "").replace("/local/", "")
                layers = f.get("TotalLayers", "?")
                print(f"  {name:<50s} {size_mb:>8.1f} MB  {layers:>4s} layers" if isinstance(layers, int) else f"  {name:<50s} {size_mb:>8.1f} MB  {str(layers):>4s} layers")
                
        elif command == "start":
            filepath = sys.argv[2]
            if not filepath.startswith("/"):
                filepath = f"/local/{filepath}"
            resp = await printer.start_print(filepath)
            print(f"Started print: {filepath}")
            print(json.dumps(resp, indent=2) if resp else "No response")
            
        elif command == "pause":
            resp = await printer.pause_print()
            print("Print paused.")
            
        elif command == "resume":
            resp = await printer.resume_print()
            print("Print resumed.")
            
        elif command == "stop":
            resp = await printer.stop_print()
            print("Print stopped.")
            
        elif command == "nozzle":
            temp = int(sys.argv[2])
            resp = await printer.set_nozzle_temp(temp)
            print(f"Nozzle target set to {temp}°C")
            
        elif command == "bed":
            temp = int(sys.argv[2])
            resp = await printer.set_bed_temp(temp)
            print(f"Bed target set to {temp}°C")
            
        elif command == "chamber":
            temp = int(sys.argv[2])
            resp = await printer.set_chamber_temp(temp)
            print(f"Chamber target set to {temp}°C")
            
        elif command == "fan":
            fan_type = sys.argv[2]
            speed = int(sys.argv[3])
            resp = await printer.set_fan_speed(fan_type, speed)
            print(f"{fan_type} set to {speed}%")
            
        elif command == "light":
            on = sys.argv[2].lower() in ("on", "1", "true", "yes")
            resp = await printer.set_light(on)
            print(f"Light {'on' if on else 'off'}")
            
        elif command == "jog":
            axis = sys.argv[2].upper()
            distance = float(sys.argv[3])
            resp = await printer.jog_axis(axis, distance)
            print(f"Jogged {axis} by {distance}mm")
            
        elif command == "home":
            axes = [a.upper() for a in sys.argv[2:]] if len(sys.argv) > 2 else None
            resp = await printer.home_axes(axes)
            print(f"Homed axes: {axes or ['X', 'Y', 'Z']}")
            
        elif command == "speed":
            pct = int(sys.argv[2])
            resp = await printer.set_print_speed(pct)
            print(f"Print speed set to {pct}%")
            
        elif command == "history":
            history = await printer.get_print_history()
            print(json.dumps(history, indent=2))
            
        else:
            print(f"Unknown command: {command}")


if __name__ == "__main__":
    asyncio.run(cli_main())
