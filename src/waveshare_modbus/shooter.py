"""Puck shooter relay sequence with a FIFO queue."""

from __future__ import annotations

import queue
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .modbus_client import ModbusClient

RELAY_ON_DURATION = 3      # seconds relay 0 and relay n are both on
RELAY_N_EXTRA_DURATION = 3 # seconds relay n stays on after relay 0 turns off


class PuckShooterQueue:
    def __init__(self, client: ModbusClient, log_callback=None):
        self._client = client
        self._log = log_callback or (lambda msg: print(msg))
        self._queue: queue.Queue[int] = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def fire(self, n: int):
        self._queue.put(n)
        self._log(f"Puck shooter {n} queued (queue size: {self._queue.qsize()})")

    def _worker(self):
        while True:
            n = self._queue.get()
            try:
                self._sequence(n)
            except Exception as e:
                self._log(f"Shooter error (puck shooter {n}): {e}")
            finally:
                self._queue.task_done()

    def _sequence(self, n: int):
        self._log(f"Firing puck shooter {n} (relay 1 + relay {n + 1})")
        self._client.relay_on(0)
        self._client.relay_on(n)
        time.sleep(RELAY_ON_DURATION)
        self._client.relay_off(0)
        self._log(f"Relay 1 off — waiting for puck shooter {n} to complete")
        time.sleep(RELAY_N_EXTRA_DURATION)
        self._client.relay_off(n)
        self._log(f"Puck shooter {n} complete")
