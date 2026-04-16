"""Modbus TCP client for Waveshare POE ETH Relay (B) 8-Channel."""

import socket
import struct
import threading


class ModbusError(Exception):
    """Modbus protocol error response."""

    CODES = {
        0x01: "Illegal Function",
        0x02: "Illegal Data Address",
        0x03: "Illegal Data Value",
        0x04: "Slave Device Failure",
        0x05: "Acknowledge",
        0x06: "Slave Device Busy",
    }

    def __init__(self, function_code: int, error_code: int):
        self.function_code = function_code
        self.error_code = error_code
        desc = self.CODES.get(error_code, "Unknown")
        super().__init__(
            f"Modbus error FC=0x{function_code:02X}: "
            f"0x{error_code:02X} ({desc})"
        )


class ModbusClient:
    """Thread-safe Modbus TCP client for Waveshare POE ETH Relay.

    Implements raw Modbus TCP protocol (no external library required).
    Supports all relay control functions: read/write coils, read inputs,
    pulse control, control modes, and device info.
    """

    NUM_CHANNELS = 8

    def __init__(
        self,
        host: str = "192.168.0.81",
        port: int = 4196,
        unit_id: int = 1,
        timeout: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._socket: socket.socket | None = None
        self._transaction_id = 0
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._socket is not None

    def connect(self) -> None:
        """Connect to the Modbus TCP device."""
        self.disconnect()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.port))
        self._socket = sock

    def disconnect(self) -> None:
        """Disconnect from the device."""
        sock = self._socket
        self._socket = None
        if sock:
            try:
                sock.close()
            except OSError:
                pass

    def _next_tid(self) -> int:
        self._transaction_id = (self._transaction_id + 1) % 0xFFFF
        return self._transaction_id

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed by remote host")
            buf += chunk
        return buf

    def _send_receive(
        self, unit_id: int, function_code: int, data: bytes
    ) -> bytes:
        """Send a Modbus TCP request and return the response PDU (FC + data).

        Raises ConnectionError on socket issues, ModbusError on protocol errors.
        """
        with self._lock:
            sock = self._socket
            if not sock:
                raise ConnectionError("Not connected to device")

            tid = self._next_tid()
            pdu = bytes([unit_id, function_code]) + data
            mbap = struct.pack(">HHH", tid, 0, len(pdu))
            frame = mbap + pdu

            try:
                sock.sendall(frame)

                header = self._recv_exact(sock, 7)
                _, _, resp_len = struct.unpack(">HHH", header[:6])

                remaining = resp_len - 1
                pdu_data = self._recv_exact(sock, remaining)

                if pdu_data[0] & 0x80:
                    ec = pdu_data[1] if len(pdu_data) > 1 else 0xFF
                    raise ModbusError(pdu_data[0] & 0x7F, ec)

                return pdu_data

            except ModbusError:
                raise
            except (OSError, ConnectionError, TimeoutError) as e:
                self._socket = None
                raise ConnectionError(f"Communication error: {e}")

    # ── Relay Control (FC 0x05: Write Single Coil) ──────────────────

    def relay_on(self, channel: int) -> None:
        """Turn ON a single relay channel (0-7)."""
        data = struct.pack(">HH", channel, 0xFF00)
        self._send_receive(self.unit_id, 0x05, data)

    def relay_off(self, channel: int) -> None:
        """Turn OFF a single relay channel (0-7)."""
        data = struct.pack(">HH", channel, 0x0000)
        self._send_receive(self.unit_id, 0x05, data)

    def relay_toggle(self, channel: int) -> None:
        """Toggle a single relay channel (0-7)."""
        data = struct.pack(">HH", channel, 0x5500)
        self._send_receive(self.unit_id, 0x05, data)

    def all_relays_on(self) -> None:
        """Turn ON all relay channels."""
        data = struct.pack(">HH", 0x00FF, 0xFF00)
        self._send_receive(self.unit_id, 0x05, data)

    def all_relays_off(self) -> None:
        """Turn OFF all relay channels."""
        data = struct.pack(">HH", 0x00FF, 0x0000)
        self._send_receive(self.unit_id, 0x05, data)

    def all_relays_toggle(self) -> None:
        """Toggle all relay channels."""
        data = struct.pack(">HH", 0x00FF, 0x5500)
        self._send_receive(self.unit_id, 0x05, data)

    # ── Pulse Control (FC 0x05 with special addresses) ──────────────

    def relay_pulse_on(self, channel: int, duration_ms: int) -> None:
        """Pulse relay ON for duration (rounded to 100ms units).

        Relay turns ON immediately, then OFF after the duration.
        """
        addr = 0x0200 + channel
        value = max(1, duration_ms // 100)
        data = struct.pack(">HH", addr, value)
        self._send_receive(self.unit_id, 0x05, data)

    def relay_pulse_off(self, channel: int, duration_ms: int) -> None:
        """Pulse relay OFF for duration (rounded to 100ms units).

        Relay turns OFF immediately, then ON after the duration.
        """
        addr = 0x0400 + channel
        value = max(1, duration_ms // 100)
        data = struct.pack(">HH", addr, value)
        self._send_receive(self.unit_id, 0x05, data)

    # ── Read Status ─────────────────────────────────────────────────

    def read_relay_status(self) -> list[bool]:
        """Read all 8 relay channel states (FC 0x01: Read Coils)."""
        data = struct.pack(">HH", 0x0000, 0x0008)
        resp = self._send_receive(self.unit_id, 0x01, data)
        status_byte = resp[2]
        return [(status_byte >> i) & 1 == 1 for i in range(self.NUM_CHANNELS)]

    def read_input_status(self) -> list[bool]:
        """Read all 8 digital input states (FC 0x02: Read Discrete Inputs)."""
        data = struct.pack(">HH", 0x0000, 0x0008)
        resp = self._send_receive(self.unit_id, 0x02, data)
        status_byte = resp[2]
        return [(status_byte >> i) & 1 == 1 for i in range(self.NUM_CHANNELS)]

    # ── Write Multiple Coils (FC 0x0F) ──────────────────────────────

    def write_all_relays(self, states: list[bool]) -> None:
        """Set all 8 relay states at once."""
        byte_val = 0
        for i, state in enumerate(states[: self.NUM_CHANNELS]):
            if state:
                byte_val |= 1 << i
        data = struct.pack(">HHB", 0x0000, 0x0008, 1) + bytes([byte_val])
        self._send_receive(self.unit_id, 0x0F, data)

    # ── Control Mode (FC 0x03/0x06: Read/Write Holding Registers) ──

    def read_control_modes(self) -> list[int]:
        """Read control modes for all 8 channels.

        Returns list of mode values: 0 = Normal, 1 = Linked.
        """
        data = struct.pack(">HH", 0x1000, 0x0008)
        resp = self._send_receive(self.unit_id, 0x03, data)
        modes = []
        for i in range(self.NUM_CHANNELS):
            mode = struct.unpack(">H", resp[2 + i * 2 : 4 + i * 2])[0]
            modes.append(mode)
        return modes

    def set_control_mode(self, channel: int, mode: int) -> None:
        """Set control mode for a single channel. 0 = Normal, 1 = Linked."""
        data = struct.pack(">HH", 0x1000 + channel, mode)
        self._send_receive(self.unit_id, 0x06, data)

    def set_all_control_modes(self, mode: int) -> None:
        """Set all channels to the same control mode (FC 0x10)."""
        reg_data = b""
        for _ in range(self.NUM_CHANNELS):
            reg_data += struct.pack(">H", mode)
        data = struct.pack(">HHB", 0x1000, 0x0008, len(reg_data)) + reg_data
        self._send_receive(self.unit_id, 0x10, data)

    # ── Device Info (FC 0x03, Unit ID 0x00) ─────────────────────────

    def read_device_address(self) -> int:
        """Read the device's Modbus address."""
        data = struct.pack(">HH", 0x4000, 0x0001)
        resp = self._send_receive(0x00, 0x03, data)
        return struct.unpack(">H", resp[2:4])[0]

    def read_software_version(self) -> int:
        """Read the device's firmware version."""
        data = struct.pack(">HH", 0x8000, 0x0001)
        resp = self._send_receive(0x00, 0x03, data)
        return struct.unpack(">H", resp[2:4])[0]
