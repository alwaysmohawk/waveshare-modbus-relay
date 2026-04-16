"""Preset storage for relay channel configurations."""

from __future__ import annotations

import json
from pathlib import Path

_PRESETS_FILE = Path(__file__).resolve().parent / "presets.json"


def _load() -> dict[str, list[bool]]:
    if _PRESETS_FILE.exists():
        try:
            data = json.loads(_PRESETS_FILE.read_text(encoding="utf-8"))
            return {
                k: v
                for k, v in data.items()
                if isinstance(v, list) and len(v) == 8
            }
        except (json.JSONDecodeError, KeyError):
            return {}
    return {}


def _save(presets: dict[str, list[bool]]) -> None:
    _PRESETS_FILE.write_text(
        json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def list_presets() -> dict[str, list[bool]]:
    return _load()


def get_preset(name: str) -> list[bool] | None:
    return _load().get(name)


def save_preset(name: str, states: list[bool]) -> None:
    presets = _load()
    presets[name] = states[:8]
    _save(presets)


def delete_preset(name: str) -> bool:
    presets = _load()
    if name in presets:
        del presets[name]
        _save(presets)
        return True
    return False
