"""REST API for Waveshare Modbus Relay Control.

Provides a full HTTP API for controlling the relay device remotely.
Runs alongside the GUI on a configurable port.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

if TYPE_CHECKING:
    from .modbus_client import ModbusClient


# ── Request / Response Models ───────────────────────────────────────


class ConnectRequest(BaseModel):
    host: str = "192.168.0.81"
    port: int = 4196
    unit_id: int = 1


PULSE_DURATION_MS = 200
PULSE_ACTION = "on"


class PulseRequest(BaseModel):
    action: str = Field(default=PULSE_ACTION, description="'on' or 'off'")
    duration_ms: int = Field(default=PULSE_DURATION_MS, ge=100, description="Duration in milliseconds (min 100)")


class BatchRequest(BaseModel):
    states: list[bool] = Field(min_length=8, max_length=8)


class ModeRequest(BaseModel):
    mode: str = Field(description="'normal' or 'linked'")


class PresetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    states: list[bool] = Field(min_length=8, max_length=8)


# ── API Factory ─────────────────────────────────────────────────────


def create_api(
    client: ModbusClient,
    log_callback: Callable[[str], None] | None = None,
) -> FastAPI:
    """Create a FastAPI application bound to the given ModbusClient."""

    app = FastAPI(
        title="Waveshare Modbus Relay API",
        description="REST API for Waveshare Modbus POE ETH Relay (B) 8-Channel",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class LogMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            t0 = time.monotonic()
            response: Response = await call_next(request)
            ms = (time.monotonic() - t0) * 1000
            if log_callback:
                log_callback(
                    f"API {request.method} {request.url.path} "
                    f"\u2192 {response.status_code} ({ms:.0f}ms)"
                )
            return response

    app.add_middleware(LogMiddleware)

    def _require_connection():
        if not client.connected:
            try:
                client.connect()
                if log_callback:
                    log_callback(f"Auto-connected to {client.host}:{client.port}")
            except Exception as e:
                raise HTTPException(503, f"Could not connect to device at {client.host}:{client.port}: {e}")

    # ── Connection ──────────────────────────────────────────────

    @app.get("/api/status", tags=["connection"])
    def get_status():
        return {
            "connected": client.connected,
            "host": client.host,
            "port": client.port,
            "unit_id": client.unit_id,
        }

    @app.post("/api/connect", tags=["connection"])
    def connect(req: ConnectRequest):
        client.host = req.host
        client.port = req.port
        client.unit_id = req.unit_id
        try:
            client.connect()
            return {"connected": True, "host": req.host, "port": req.port}
        except Exception as e:
            raise HTTPException(500, f"Connection failed: {e}")

    @app.post("/api/disconnect", tags=["connection"])
    def disconnect():
        client.disconnect()
        return {"connected": False}

    # ── Relay Read ──────────────────────────────────────────────

    @app.get("/api/relays", tags=["relays"])
    def get_all_relays():
        _require_connection()
        try:
            states = client.read_relay_status()
            return {
                "relays": [
                    {"channel": i, "state": s} for i, s in enumerate(states)
                ]
            }
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/api/relays/{channel}", tags=["relays"])
    def get_relay(channel: int):
        if not 0 <= channel <= 7:
            raise HTTPException(400, "Channel must be 0-7")
        _require_connection()
        try:
            states = client.read_relay_status()
            return {"channel": channel, "state": states[channel]}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Relay Write (single channel) ────────────────────────────

    @app.post("/api/relays/{channel}/on", tags=["relays"])
    def relay_on(channel: int):
        if not 0 <= channel <= 7:
            raise HTTPException(400, "Channel must be 0-7")
        _require_connection()
        try:
            client.relay_on(channel)
            return {"channel": channel, "action": "on"}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post("/api/relays/{channel}/off", tags=["relays"])
    def relay_off(channel: int):
        if not 0 <= channel <= 7:
            raise HTTPException(400, "Channel must be 0-7")
        _require_connection()
        try:
            client.relay_off(channel)
            return {"channel": channel, "action": "off"}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post("/api/relays/{channel}/toggle", tags=["relays"])
    def relay_toggle(channel: int):
        if not 0 <= channel <= 7:
            raise HTTPException(400, "Channel must be 0-7")
        _require_connection()
        try:
            client.relay_toggle(channel)
            return {"channel": channel, "action": "toggle"}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Relay Write (all channels) ──────────────────────────────

    @app.post("/api/relays/all/on", tags=["relays"])
    def all_on():
        _require_connection()
        try:
            client.all_relays_on()
            return {"action": "all_on"}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post("/api/relays/all/off", tags=["relays"])
    def all_off():
        _require_connection()
        try:
            client.all_relays_off()
            return {"action": "all_off"}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post("/api/relays/all/toggle", tags=["relays"])
    def all_toggle():
        _require_connection()
        try:
            client.all_relays_toggle()
            return {"action": "all_toggle"}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Batch Set ───────────────────────────────────────────────

    @app.post("/api/relays/batch", tags=["relays"])
    def batch_set(req: BatchRequest):
        _require_connection()
        try:
            client.write_all_relays(req.states)
            return {"action": "batch_set", "states": req.states}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Pulse Control ───────────────────────────────────────────

    @app.post("/api/relays/{channel}/pulse", tags=["pulse"])
    def pulse(channel: int, req: PulseRequest = Body(default_factory=PulseRequest)):
        if not 0 <= channel <= 7:
            raise HTTPException(400, "Channel must be 0-7")
        _require_connection()
        try:
            if req.action == "on":
                client.relay_pulse_on(channel, req.duration_ms)
            elif req.action == "off":
                client.relay_pulse_off(channel, req.duration_ms)
            else:
                raise HTTPException(400, "action must be 'on' or 'off'")
            return {
                "channel": channel,
                "action": f"pulse_{req.action}",
                "duration_ms": req.duration_ms,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Digital Inputs ──────────────────────────────────────────

    @app.get("/api/inputs", tags=["inputs"])
    def get_inputs():
        _require_connection()
        try:
            states = client.read_input_status()
            return {
                "inputs": [
                    {"channel": i, "state": s} for i, s in enumerate(states)
                ]
            }
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/api/inputs/{channel}", tags=["inputs"])
    def get_input(channel: int):
        if not 0 <= channel <= 7:
            raise HTTPException(400, "Channel must be 0-7")
        _require_connection()
        try:
            states = client.read_input_status()
            return {"channel": channel, "state": states[channel]}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Control Modes ───────────────────────────────────────────

    @app.get("/api/modes", tags=["modes"])
    def get_modes():
        _require_connection()
        try:
            modes = client.read_control_modes()
            names = {0: "normal", 1: "linked"}
            return {
                "modes": [
                    {"channel": i, "mode": names.get(m, str(m))}
                    for i, m in enumerate(modes)
                ]
            }
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.put("/api/modes/{channel}", tags=["modes"])
    def set_mode(channel: int, req: ModeRequest):
        if not 0 <= channel <= 7:
            raise HTTPException(400, "Channel must be 0-7")
        _require_connection()
        mode_val = {"normal": 0, "linked": 1}.get(req.mode)
        if mode_val is None:
            raise HTTPException(400, "mode must be 'normal' or 'linked'")
        try:
            client.set_control_mode(channel, mode_val)
            return {"channel": channel, "mode": req.mode}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Device Info ─────────────────────────────────────────────

    @app.get("/api/device/info", tags=["device"])
    def get_device_info():
        _require_connection()
        info = {}
        try:
            info["address"] = client.read_device_address()
        except Exception:
            info["address"] = None
        try:
            info["firmware_version"] = client.read_software_version()
        except Exception:
            info["firmware_version"] = None
        return info

    # ── Presets ─────────────────────────────────────────────

    @app.get("/api/presets", tags=["presets"])
    def list_presets_endpoint():
        from .presets import list_presets

        data = list_presets()
        return {"presets": [{"name": k, "states": v} for k, v in data.items()]}

    @app.post("/api/presets", tags=["presets"])
    def create_preset(req: PresetCreateRequest):
        from .presets import save_preset

        save_preset(req.name, req.states)
        return {"name": req.name, "states": req.states}

    @app.delete("/api/presets/{name}", tags=["presets"])
    def delete_preset_endpoint(name: str):
        from .presets import delete_preset

        if not delete_preset(name):
            raise HTTPException(404, f"Preset '{name}' not found")
        return {"deleted": name}

    @app.post("/api/presets/{name}/apply", tags=["presets"])
    def apply_preset(name: str):
        from .presets import get_preset

        _require_connection()
        states = get_preset(name)
        if states is None:
            raise HTTPException(404, f"Preset '{name}' not found")
        try:
            client.write_all_relays(states)
            return {"applied": name, "states": states}
        except Exception as e:
            raise HTTPException(500, str(e))

    return app
