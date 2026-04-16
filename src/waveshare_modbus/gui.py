"""Waveshare Modbus Relay Controller - GUI Application.

CustomTkinter-based GUI with Waveshare brand colors (black, green, white).
Features: relay control, input monitoring, pulse control, REST API server.
"""

from __future__ import annotations

import threading
from datetime import datetime

import customtkinter as ctk
import uvicorn

from .api import create_api
from .modbus_client import ModbusClient
from . import presets

# ── Waveshare Brand Color Palette ───────────────────────────────────

WS = {
    "bg": "#0D0D0D",
    "bg_sec": "#161616",
    "bg_card": "#1E1E1E",
    "bg_card_on": "#0E2818",
    "border": "#2A2A2A",
    "border_on": "#00B050",
    "green": "#00B050",
    "green_hover": "#00D45F",
    "green_dark": "#008A3E",
    "white": "#FFFFFF",
    "gray": "#999999",
    "gray_dark": "#555555",
    "gray_darker": "#333333",
    "red": "#E74C3C",
    "red_hover": "#FF5C4D",
    "led_on": "#00FF6A",
    "led_off": "#444444",
    "header_text": "#062E15",
}

FONT_MONO = "Consolas"
FONT_UI = "Segoe UI"


# ── Relay Card Widget ───────────────────────────────────────────────


class RelayCard(ctk.CTkFrame):
    """Compact horizontal card for a single relay channel."""

    def __init__(self, master, channel: int, on_toggle, on_on, on_off):
        super().__init__(
            master,
            fg_color=WS["bg_card"],
            corner_radius=6,
            border_width=1,
            border_color=WS["border"],
        )
        self.channel = channel
        self._state = False
        self._preview = None
        self._on_toggle = on_toggle
        self._on_on = on_on
        self._on_off = on_off
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text=f"CH {channel}",
            font=ctk.CTkFont(family=FONT_MONO, size=12, weight="bold"),
            text_color=WS["white"],
            width=44,
        ).grid(row=0, column=0, padx=(8, 2), pady=6)

        self.status = ctk.CTkLabel(
            self,
            text="\u25CF OFF",
            font=ctk.CTkFont(family=FONT_MONO, size=12, weight="bold"),
            text_color=WS["led_off"],
            anchor="w",
        )
        self.status.grid(row=0, column=1, padx=2, pady=6, sticky="w")

        small_btn_kw = dict(
            width=40,
            height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            corner_radius=5,
        )

        ctk.CTkButton(
            self,
            text="ON",
            fg_color=WS["bg_card"],
            hover_color=WS["gray_darker"],
            border_width=1,
            border_color=WS["green"],
            text_color=WS["green"],
            command=lambda: self._on_on(self.channel),
            **small_btn_kw,
        ).grid(row=0, column=2, padx=(2, 2), pady=6)

        ctk.CTkButton(
            self,
            text="OFF",
            fg_color=WS["bg_card"],
            hover_color=WS["gray_darker"],
            border_width=1,
            border_color=WS["red"],
            text_color=WS["red"],
            command=lambda: self._on_off(self.channel),
            **small_btn_kw,
        ).grid(row=0, column=3, padx=(0, 2), pady=6)

        self.btn = ctk.CTkButton(
            self,
            text="TOGGLE",
            width=70,
            height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=WS["green"],
            hover_color=WS["green_hover"],
            text_color=WS["bg"],
            corner_radius=5,
            command=lambda: self._on_toggle(self.channel),
        )
        self.btn.grid(row=0, column=4, padx=(2, 8), pady=6)

    def _update_border(self):
        if self._preview:
            self.configure(border_color=WS["red"], border_width=2)
        else:
            border = WS["border_on"] if self._state else WS["border"]
            self.configure(border_color=border, border_width=1)

    def set_state(self, state: bool):
        if state == self._state:
            return
        self._state = state
        if state:
            self.configure(fg_color=WS["bg_card_on"])
            self.status.configure(text="\u25CF ON", text_color=WS["led_on"])
        else:
            self.configure(fg_color=WS["bg_card"])
            self.status.configure(text="\u25CF OFF", text_color=WS["led_off"])
        self._update_border()

    def set_preview(self, target: bool | None):
        self._preview = target
        self._update_border()


# ── Main Application Window ─────────────────────────────────────────


class WaveshareApp(ctk.CTk):
    """Waveshare Modbus Relay Controller main window."""

    def __init__(self):
        super().__init__()

        self.title("Waveshare Modbus Relay Controller")
        self.geometry("960x820")
        self.minsize(800, 700)
        self.configure(fg_color=WS["bg"])

        self.client = ModbusClient()
        self._api_log_cb = lambda msg: self.after(0, self._log, msg)
        self.api_app = create_api(self.client, log_callback=self._api_log_cb)
        self._api_server: uvicorn.Server | None = None

        self._build_header()

        self.content = ctk.CTkFrame(self, fg_color=WS["bg"])
        self.content.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.content.grid_columnconfigure(0, weight=1)

        self._selected_preset = None
        self._new_states = [False] * 8
        self._new_ch_btns: list[ctk.CTkButton] = []

        self._build_connection()
        self._build_api()
        self._build_pulse()
        self._build_relays()
        self._build_presets()
        self._build_inputs()
        self._build_log()

        self._start_api()
        self._poll()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI Construction ─────────────────────────────────────────

    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color=WS["green"], corner_radius=0, height=38)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        ctk.CTkLabel(
            bar,
            text="  \u25A0  WAVESHARE",
            font=ctk.CTkFont(family=FONT_UI, size=15, weight="bold"),
            text_color=WS["bg"],
        ).pack(side="left", padx=(10, 4))

        ctk.CTkLabel(
            bar,
            text="Modbus POE ETH Relay Controller",
            font=ctk.CTkFont(family=FONT_UI, size=11),
            text_color=WS["header_text"],
        ).pack(side="left")

        ctk.CTkLabel(
            bar,
            text="8-CH  ",
            font=ctk.CTkFont(family=FONT_MONO, size=11, weight="bold"),
            text_color=WS["bg"],
        ).pack(side="right", padx=12)

    def _section(self, text: str):
        ctk.CTkLabel(
            self.content,
            text=text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=WS["green"],
            anchor="w",
        ).pack(fill="x", pady=(8, 2), padx=2)

    def _build_connection(self):
        self._section("CONNECTION")
        frame = ctk.CTkFrame(
            self.content, fg_color=WS["bg_sec"], corner_radius=10
        )
        frame.pack(fill="x")

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)

        entry_kw = dict(
            height=28,
            fg_color=WS["bg_card"],
            border_color=WS["border"],
            text_color=WS["white"],
            font=ctk.CTkFont(family=FONT_MONO, size=12),
        )
        label_kw = dict(
            text_color=WS["gray"], font=ctk.CTkFont(size=12)
        )

        ctk.CTkLabel(row, text="Host:", **label_kw).pack(side="left")
        self.host_entry = ctk.CTkEntry(row, width=150, **entry_kw)
        self.host_entry.insert(0, "192.168.0.81")
        self.host_entry.pack(side="left", padx=(6, 14))

        ctk.CTkLabel(row, text="Port:", **label_kw).pack(side="left")
        self.port_entry = ctk.CTkEntry(row, width=70, **entry_kw)
        self.port_entry.insert(0, "4196")
        self.port_entry.pack(side="left", padx=(6, 14))

        ctk.CTkLabel(row, text="Unit ID:", **label_kw).pack(side="left")
        self.unit_entry = ctk.CTkEntry(row, width=50, **entry_kw)
        self.unit_entry.insert(0, "1")
        self.unit_entry.pack(side="left", padx=(6, 14))

        self.connect_btn = ctk.CTkButton(
            row,
            text="Connect",
            width=100,
            height=28,
            fg_color=WS["green"],
            hover_color=WS["green_hover"],
            text_color=WS["bg"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._toggle_connection,
        )
        self.connect_btn.pack(side="left", padx=(6, 14))

        self.conn_led = ctk.CTkLabel(
            row,
            text="\u25CF",
            font=ctk.CTkFont(size=16),
            text_color=WS["red"],
        )
        self.conn_led.pack(side="left", padx=(0, 4))

        self.conn_label = ctk.CTkLabel(
            row,
            text="Disconnected",
            text_color=WS["gray"],
            font=ctk.CTkFont(size=12),
        )
        self.conn_label.pack(side="left")

    def _build_relays(self):
        self._section("RELAY CHANNELS")
        frame = ctk.CTkFrame(
            self.content, fg_color=WS["bg_sec"], corner_radius=10
        )
        frame.pack(fill="x")

        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x", padx=6, pady=(4, 0))
        for c in range(4):
            grid.grid_columnconfigure(c, weight=1)

        self.relay_cards: list[RelayCard] = []
        for i in range(8):
            card = RelayCard(grid, i, self._toggle_relay, self._relay_on, self._relay_off)
            card.grid(row=i // 4, column=i % 4, padx=3, pady=3, sticky="ew")
            self.relay_cards.append(card)

        bulk = ctk.CTkFrame(frame, fg_color="transparent")
        bulk.pack(fill="x", padx=10, pady=(2, 6))

        outline_kw = dict(
            width=110,
            height=28,
            fg_color=WS["bg_card"],
            hover_color=WS["gray_darker"],
            border_width=1,
            border_color=WS["green"],
            text_color=WS["green"],
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=6,
        )

        ctk.CTkButton(
            bulk, text="ALL ON", command=self._all_on, **outline_kw
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            bulk, text="ALL OFF", command=self._all_off, **outline_kw
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            bulk, text="TOGGLE ALL", command=self._toggle_all, **outline_kw
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            bulk,
            text="\u27F3  REFRESH",
            width=90,
            height=28,
            fg_color="transparent",
            hover_color=WS["gray_darker"],
            text_color=WS["gray"],
            font=ctk.CTkFont(size=11),
            command=self._refresh,
        ).pack(side="right", padx=4)

    def _build_inputs(self):
        self._section("DIGITAL INPUTS")
        frame = ctk.CTkFrame(
            self.content, fg_color=WS["bg_sec"], corner_radius=10
        )
        frame.pack(fill="x")

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=6)
        for c in range(8):
            row.grid_columnconfigure(c, weight=1)

        self.input_leds: list[ctk.CTkLabel] = []
        for i in range(8):
            cell = ctk.CTkFrame(
                row, fg_color=WS["bg_card"], corner_radius=6
            )
            cell.grid(row=0, column=i, padx=3, pady=1, sticky="nsew")

            ctk.CTkLabel(
                cell,
                text=f"IN {i}",
                font=ctk.CTkFont(family=FONT_MONO, size=10),
                text_color=WS["gray"],
            ).pack(pady=(4, 0))

            led = ctk.CTkLabel(
                cell,
                text="\u25CF LOW",
                font=ctk.CTkFont(family=FONT_MONO, size=11, weight="bold"),
                text_color=WS["led_off"],
            )
            led.pack(pady=(1, 4))
            self.input_leds.append(led)

    def _build_pulse(self):
        self._section("PULSE CONTROL")
        frame = ctk.CTkFrame(
            self.content, fg_color=WS["bg_sec"], corner_radius=10
        )
        frame.pack(fill="x")

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)

        lkw = dict(text_color=WS["gray"], font=ctk.CTkFont(size=12))

        ctk.CTkLabel(row, text="Channel:", **lkw).pack(side="left")
        self.pulse_ch = ctk.CTkOptionMenu(
            row,
            values=[str(i) for i in range(8)],
            width=60,
            height=28,
            fg_color=WS["bg_card"],
            button_color=WS["green"],
            button_hover_color=WS["green_hover"],
            text_color=WS["white"],
            font=ctk.CTkFont(family=FONT_MONO, size=12),
            dropdown_fg_color=WS["bg_card"],
            dropdown_text_color=WS["white"],
            dropdown_hover_color=WS["green_dark"],
        )
        self.pulse_ch.pack(side="left", padx=(6, 16))

        ctk.CTkLabel(row, text="Duration (ms):", **lkw).pack(side="left")
        self.pulse_dur = ctk.CTkEntry(
            row,
            width=80,
            height=28,
            fg_color=WS["bg_card"],
            border_color=WS["border"],
            text_color=WS["white"],
            font=ctk.CTkFont(family=FONT_MONO, size=12),
        )
        self.pulse_dur.insert(0, "1000")
        self.pulse_dur.pack(side="left", padx=(6, 16))

        ctk.CTkButton(
            row,
            text="PULSE ON",
            width=100,
            height=28,
            fg_color=WS["green"],
            hover_color=WS["green_hover"],
            text_color=WS["bg"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._pulse_on,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            row,
            text="PULSE OFF",
            width=100,
            height=28,
            fg_color=WS["bg_card"],
            hover_color=WS["gray_darker"],
            border_width=1,
            border_color=WS["green"],
            text_color=WS["green"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._pulse_off,
        ).pack(side="left", padx=4)

    def _build_presets(self):
        self._section("PRESETS")
        frame = ctk.CTkFrame(
            self.content, fg_color=WS["bg_sec"], corner_radius=10
        )
        frame.pack(fill="x")

        # ── Row 1: Select / Preview / Apply / Delete ──
        sel_row = ctk.CTkFrame(frame, fg_color="transparent")
        sel_row.pack(fill="x", padx=12, pady=(8, 0))

        lkw = dict(text_color=WS["gray"], font=ctk.CTkFont(size=12))

        ctk.CTkLabel(sel_row, text="Preset:", **lkw).pack(side="left")
        self.preset_dropdown = ctk.CTkOptionMenu(
            sel_row,
            values=["(none)"],
            width=150,
            height=28,
            fg_color=WS["bg_card"],
            button_color=WS["green"],
            button_hover_color=WS["green_hover"],
            text_color=WS["white"],
            font=ctk.CTkFont(family=FONT_MONO, size=12),
            dropdown_fg_color=WS["bg_card"],
            dropdown_text_color=WS["white"],
            dropdown_hover_color=WS["green_dark"],
            command=self._on_preset_selected,
        )
        self.preset_dropdown.pack(side="left", padx=(6, 12))

        self.preset_dots: list[ctk.CTkLabel] = []
        for i in range(8):
            dot = ctk.CTkLabel(
                sel_row,
                text="\u25CF",
                font=ctk.CTkFont(size=12),
                text_color=WS["led_off"],
                width=16,
            )
            dot.pack(side="left")
            self.preset_dots.append(dot)

        ctk.CTkButton(
            sel_row,
            text="APPLY",
            width=70,
            height=28,
            fg_color=WS["green"],
            hover_color=WS["green_hover"],
            text_color=WS["bg"],
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=5,
            command=self._apply_preset,
        ).pack(side="left", padx=(12, 4))

        ctk.CTkButton(
            sel_row,
            text="\u2715 DEL",
            width=56,
            height=28,
            fg_color=WS["bg_card"],
            hover_color=WS["red_hover"],
            border_width=1,
            border_color=WS["red"],
            text_color=WS["red"],
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=5,
            command=self._delete_preset,
        ).pack(side="left", padx=4)

        # ── Row 2: New preset creator ──
        sep = ctk.CTkFrame(frame, fg_color=WS["border"], height=1)
        sep.pack(fill="x", padx=10, pady=(6, 0))

        creator = ctk.CTkFrame(frame, fg_color="transparent")
        creator.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(creator, text="New:", **lkw).pack(side="left")
        self.preset_name_entry = ctk.CTkEntry(
            creator,
            width=120,
            height=28,
            fg_color=WS["bg_card"],
            border_color=WS["border"],
            text_color=WS["white"],
            font=ctk.CTkFont(family=FONT_MONO, size=12),
            placeholder_text="name",
        )
        self.preset_name_entry.pack(side="left", padx=(6, 10))

        for i in range(8):
            btn = ctk.CTkButton(
                creator,
                text=f"{i}",
                width=30,
                height=24,
                font=ctk.CTkFont(family=FONT_MONO, size=10, weight="bold"),
                fg_color=WS["led_off"],
                hover_color=WS["gray_darker"],
                text_color=WS["gray"],
                corner_radius=4,
                command=lambda ch=i: self._toggle_new_ch(ch),
            )
            btn.pack(side="left", padx=1)
            self._new_ch_btns.append(btn)

        small_kw = dict(
            height=24,
            font=ctk.CTkFont(size=10),
            corner_radius=4,
            fg_color="transparent",
            hover_color=WS["gray_darker"],
            text_color=WS["gray"],
        )

        ctk.CTkButton(
            creator, text="ALL", width=34, command=self._new_select_all, **small_kw
        ).pack(side="left", padx=(8, 1))
        ctk.CTkButton(
            creator, text="NONE", width=40, command=self._new_deselect_all, **small_kw
        ).pack(side="left", padx=1)
        ctk.CTkButton(
            creator, text="CURRENT", width=64, command=self._load_current, **small_kw
        ).pack(side="left", padx=1)

        ctk.CTkButton(
            creator,
            text="SAVE",
            width=60,
            height=24,
            fg_color=WS["green"],
            hover_color=WS["green_hover"],
            text_color=WS["bg"],
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=4,
            command=self._save_new_preset,
        ).pack(side="right", padx=(8, 0))

        self._refresh_preset_dropdown()

    # ── Preset Management ──────────────────────────────────

    def _refresh_preset_dropdown(self):
        data = presets.list_presets()
        names = list(data.keys()) if data else []
        self.preset_dropdown.configure(values=["(none)"] + names)
        self.preset_dropdown.set("(none)")
        self._clear_preview()

    def _on_preset_selected(self, name: str):
        if name == "(none)":
            self._clear_preview()
            for dot in self.preset_dots:
                dot.configure(text_color=WS["led_off"])
            return

        states = presets.get_preset(name)
        if states is None:
            return

        self._selected_preset = name
        for i, dot in enumerate(self.preset_dots):
            dot.configure(text_color=WS["green"] if states[i] else WS["led_off"])
        for i, card in enumerate(self.relay_cards):
            card.set_preview(states[i])
        self._log(f"Preview: {name}")

    def _clear_preview(self):
        self._selected_preset = None
        for card in self.relay_cards:
            card.set_preview(None)
        for dot in self.preset_dots:
            dot.configure(text_color=WS["led_off"])

    def _apply_preset(self):
        name = self.preset_dropdown.get()
        if name == "(none)":
            self._log("No preset selected")
            return
        states = presets.get_preset(name)
        if states is None:
            self._log(f"Preset '{name}' not found")
            return
        self._clear_preview()
        self.preset_dropdown.set("(none)")
        self._run_cmd(
            lambda: self.client.write_all_relays(states),
            f"Preset '{name}' applied",
        )

    def _delete_preset(self):
        name = self.preset_dropdown.get()
        if name == "(none)":
            self._log("No preset selected")
            return
        presets.delete_preset(name)
        self._clear_preview()
        self._refresh_preset_dropdown()
        self._log(f"Preset '{name}' deleted")

    def _toggle_new_ch(self, ch: int):
        self._new_states[ch] = not self._new_states[ch]
        self._update_new_ch_btn(ch)

    def _update_new_ch_btn(self, ch: int):
        if self._new_states[ch]:
            self._new_ch_btns[ch].configure(
                fg_color=WS["green"], text_color=WS["bg"]
            )
        else:
            self._new_ch_btns[ch].configure(
                fg_color=WS["led_off"], text_color=WS["gray"]
            )

    def _new_select_all(self):
        self._new_states = [True] * 8
        for i in range(8):
            self._update_new_ch_btn(i)

    def _new_deselect_all(self):
        self._new_states = [False] * 8
        for i in range(8):
            self._update_new_ch_btn(i)

    def _load_current(self):
        for i, card in enumerate(self.relay_cards):
            self._new_states[i] = card._state
            self._update_new_ch_btn(i)

    def _save_new_preset(self):
        name = self.preset_name_entry.get().strip()
        if not name:
            self._log("Preset name is required")
            return
        presets.save_preset(name, list(self._new_states))
        self.preset_name_entry.delete(0, "end")
        self._new_deselect_all()
        self._refresh_preset_dropdown()
        self._log(f"Preset '{name}' saved")

    def _build_api(self):
        self._section("REST API SERVER")
        frame = ctk.CTkFrame(
            self.content, fg_color=WS["bg_sec"], corner_radius=10
        )
        frame.pack(fill="x")

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(
            row, text="Host:", text_color=WS["gray"], font=ctk.CTkFont(size=12)
        ).pack(side="left")

        self.api_host = ctk.CTkEntry(
            row,
            width=120,
            height=28,
            fg_color=WS["bg_card"],
            border_color=WS["border"],
            text_color=WS["white"],
            font=ctk.CTkFont(family=FONT_MONO, size=12),
        )
        self.api_host.insert(0, "0.0.0.0")
        self.api_host.pack(side="left", padx=(6, 14))

        ctk.CTkLabel(
            row, text="Port:", text_color=WS["gray"], font=ctk.CTkFont(size=12)
        ).pack(side="left")

        self.api_port = ctk.CTkEntry(
            row,
            width=70,
            height=28,
            fg_color=WS["bg_card"],
            border_color=WS["border"],
            text_color=WS["white"],
            font=ctk.CTkFont(family=FONT_MONO, size=12),
        )
        self.api_port.insert(0, "8001")
        self.api_port.pack(side="left", padx=(6, 14))

        self.api_btn = ctk.CTkButton(
            row,
            text="Start API",
            width=100,
            height=28,
            fg_color=WS["green"],
            hover_color=WS["green_hover"],
            text_color=WS["bg"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._toggle_api,
        )
        self.api_btn.pack(side="left", padx=(0, 14))

        self.api_led = ctk.CTkLabel(
            row,
            text="\u25CF",
            font=ctk.CTkFont(size=16),
            text_color=WS["gray_dark"],
        )
        self.api_led.pack(side="left", padx=(0, 4))

        self.api_label = ctk.CTkLabel(
            row,
            text="Stopped",
            text_color=WS["gray"],
            font=ctk.CTkFont(size=12),
        )
        self.api_label.pack(side="left")

        self.api_url_value = ""
        self.api_url = ctk.CTkLabel(
            row,
            text="",
            text_color=WS["green"],
            font=ctk.CTkFont(family=FONT_MONO, size=11, underline=True),
            cursor="hand2",
        )
        self.api_url.pack(side="right", padx=8)
        self.api_url.bind("<Button-1>", self._open_api_url)

    def _build_log(self):
        self._section("LOG")
        self.log_box = ctk.CTkTextbox(
            self.content,
            height=80,
            fg_color=WS["bg_card"],
            text_color=WS["gray"],
            font=ctk.CTkFont(family=FONT_MONO, size=11),
            corner_radius=8,
            border_width=1,
            border_color=WS["border"],
            wrap="word",
        )
        self.log_box.pack(fill="both", expand=True, pady=(0, 2))
        self.log_box.configure(state="disabled")
        self._log("Waveshare Modbus Relay Controller v1.0.0 ready")

    # ── Connection ──────────────────────────────────────────────

    def _toggle_connection(self):
        if self.client.connected:
            self._do_disconnect()
        else:
            self._do_connect()

    def _do_connect(self):
        try:
            host = self.host_entry.get().strip()
            port = int(self.port_entry.get().strip())
            uid = int(self.unit_entry.get().strip())
        except ValueError:
            self._log("Invalid connection parameters")
            return

        self.client.host = host
        self.client.port = port
        self.client.unit_id = uid

        self._log(f"Connecting to {host}:{port} ...")
        self.connect_btn.configure(state="disabled")

        def work():
            try:
                self.client.connect()
                self.after(0, self._on_connected)
            except Exception as e:
                self.after(0, self._on_connect_fail, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _on_connected(self):
        self.connect_btn.configure(
            state="normal", text="Disconnect", fg_color=WS["red"], hover_color=WS["red_hover"]
        )
        self.conn_led.configure(text_color=WS["green"])
        self.conn_label.configure(text="Connected", text_color=WS["green"])
        self._log(f"Connected to {self.client.host}:{self.client.port}")
        self._refresh()

    def _on_connect_fail(self, err: str):
        self.connect_btn.configure(state="normal")
        self.conn_led.configure(text_color=WS["red"])
        self.conn_label.configure(text="Failed", text_color=WS["red"])
        self._log(f"Connection failed: {err}")

    def _do_disconnect(self):
        self.client.disconnect()
        self.connect_btn.configure(
            text="Connect", fg_color=WS["green"], hover_color=WS["green_hover"]
        )
        self.conn_led.configure(text_color=WS["red"])
        self.conn_label.configure(text="Disconnected", text_color=WS["gray"])
        for card in self.relay_cards:
            card.set_state(False)
        for led in self.input_leds:
            led.configure(text="\u25CF LOW", text_color=WS["led_off"])
        self._log("Disconnected")

    def _on_connection_lost(self):
        self.client.disconnect()
        self.connect_btn.configure(
            text="Connect", fg_color=WS["green"], hover_color=WS["green_hover"]
        )
        self.conn_led.configure(text_color=WS["red"])
        self.conn_label.configure(text="Connection lost", text_color=WS["red"])
        for card in self.relay_cards:
            card.set_state(False)
        for led in self.input_leds:
            led.configure(text="\u25CF LOW", text_color=WS["led_off"])
        self._log("Connection lost")

    # ── Relay Actions ───────────────────────────────────────────

    def _run_cmd(self, fn, success_msg: str = "", refresh: bool = True):
        """Run a Modbus command in a background thread."""
        if not self.client.connected:
            self._log("Not connected")
            return

        def work():
            try:
                fn()
                if success_msg:
                    self.after(0, self._log, success_msg)
                if refresh:
                    self.after(80, self._refresh)
            except ConnectionError:
                self.after(0, self._on_connection_lost)
            except Exception as e:
                self.after(0, self._log, f"Error: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _relay_on(self, ch: int):
        self._run_cmd(lambda: self.client.relay_on(ch), f"CH{ch} ON")

    def _relay_off(self, ch: int):
        self._run_cmd(lambda: self.client.relay_off(ch), f"CH{ch} OFF")

    def _toggle_relay(self, ch: int):
        self._run_cmd(lambda: self.client.relay_toggle(ch), f"CH{ch} toggled")

    def _all_on(self):
        self._run_cmd(self.client.all_relays_on, "All relays ON")

    def _all_off(self):
        self._run_cmd(self.client.all_relays_off, "All relays OFF")

    def _toggle_all(self):
        self._run_cmd(self.client.all_relays_toggle, "All relays toggled")

    def _pulse_on(self):
        try:
            ch = int(self.pulse_ch.get())
            dur = int(self.pulse_dur.get())
        except ValueError:
            self._log("Invalid pulse parameters")
            return
        self._run_cmd(
            lambda: self.client.relay_pulse_on(ch, dur),
            f"Pulse ON  CH{ch} {dur}ms",
        )

    def _pulse_off(self):
        try:
            ch = int(self.pulse_ch.get())
            dur = int(self.pulse_dur.get())
        except ValueError:
            self._log("Invalid pulse parameters")
            return
        self._run_cmd(
            lambda: self.client.relay_pulse_off(ch, dur),
            f"Pulse OFF CH{ch} {dur}ms",
        )

    # ── Status Polling ──────────────────────────────────────────

    def _refresh(self):
        if not self.client.connected:
            return

        def work():
            try:
                relays = self.client.read_relay_status()
                inputs = self.client.read_input_status()
                self.after(0, self._update_display, relays, inputs)
            except ConnectionError:
                self.after(0, self._on_connection_lost)
            except Exception as e:
                self.after(0, self._log, f"Poll error: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _update_display(self, relays: list[bool], inputs: list[bool]):
        for i, state in enumerate(relays):
            self.relay_cards[i].set_state(state)
        for i, state in enumerate(inputs):
            if state:
                self.input_leds[i].configure(text="\u25CF HIGH", text_color=WS["led_on"])
            else:
                self.input_leds[i].configure(text="\u25CF LOW", text_color=WS["led_off"])

    def _poll(self):
        if self.client.connected:
            self._refresh()
        self.after(2000, self._poll)

    # ── API Server ──────────────────────────────────────────────

    def _toggle_api(self):
        if self._api_server:
            self._stop_api()
        else:
            self._start_api()

    def _start_api(self):
        try:
            host = self.api_host.get().strip() or "0.0.0.0"
            port = int(self.api_port.get().strip())
        except ValueError:
            self._log("Invalid API port")
            return

        config = uvicorn.Config(
            self.api_app, host=host, port=port, log_level="warning"
        )
        self._api_server = uvicorn.Server(config)
        threading.Thread(target=self._api_server.run, daemon=True).start()

        display_host = "localhost" if host in ("0.0.0.0", "") else host
        self.api_url_value = f"http://{display_host}:{port}/docs"

        self.api_btn.configure(
            text="Stop API", fg_color=WS["red"], hover_color=WS["red_hover"]
        )
        self.api_led.configure(text_color=WS["green"])
        self.api_label.configure(text="Running", text_color=WS["green"])
        self.api_url.configure(text=self.api_url_value)
        self._log(f"API server started on {host}:{port} \u2014 Swagger at /docs")

    def _stop_api(self):
        if self._api_server:
            self._api_server.should_exit = True
            self._api_server = None
        self.api_btn.configure(
            text="Start API", fg_color=WS["green"], hover_color=WS["green_hover"]
        )
        self.api_led.configure(text_color=WS["gray_dark"])
        self.api_label.configure(text="Stopped", text_color=WS["gray"])
        self.api_url.configure(text="")
        self.api_url_value = ""
        self._log("API server stopped")

    def _open_api_url(self, _event=None):
        if not self.api_url_value:
            return
        self.clipboard_clear()
        self.clipboard_append(self.api_url_value)
        self._log(f"Copied to clipboard: {self.api_url_value}")

    # ── Logging ─────────────────────────────────────────────────

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ── Cleanup ─────────────────────────────────────────────────

    def _on_close(self):
        if self._api_server:
            self._api_server.should_exit = True
        self.client.disconnect()
        self.destroy()


# ── Entry Point ─────────────────────────────────────────────────────


def run():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
    app = WaveshareApp()
    app.mainloop()
