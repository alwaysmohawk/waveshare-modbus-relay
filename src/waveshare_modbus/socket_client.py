"""Socket.IO client — listens for shot:fire events from the Node server."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import socketio

if TYPE_CHECKING:
    from .shooter import PuckShooterQueue

RECONNECT_DELAY = 5  # seconds between reconnect attempts


def start_socket_client(url: str, shooter: PuckShooterQueue, log_callback=None):
    log = log_callback or (lambda msg: print(msg))
    sio = socketio.Client(reconnection=False)

    @sio.event
    def connect():
        log(f"Socket.IO connected to {url}")

    @sio.event
    def disconnect():
        log(f"Socket.IO disconnected from {url}")

    @sio.on("shot:fire")
    def on_shot_fire(data):
        n = data.get("puck-shooter")
        if n is None:
            log("shot:fire received but missing puck-shooter field — ignoring")
            return
        log(f"shot:fire received for puck shooter {n} (timestamp: {data.get('timestamp')})")
        shooter.fire(n)

    def run():
        while True:
            try:
                sio.connect(url)
                sio.wait()
            except Exception as e:
                log(f"Socket.IO error: {e} — retrying in {RECONNECT_DELAY}s")
            time.sleep(RECONNECT_DELAY)

    threading.Thread(target=run, daemon=True).start()
    return sio
