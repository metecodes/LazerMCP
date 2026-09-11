"""Persisted kerf calibration per machine + material. Human measurement only."""

from __future__ import annotations

from typing import Any

from physical import NOMINAL_BAR_MM, read_physical
from studio_store import now_iso, read_json, write_json


def _load() -> list[dict[str, Any]]:
    raw = read_json("calibrations.json", [])
    return raw if isinstance(raw, list) else []


def record_calibration(parameters: dict[str, Any] | None, physical: dict[str, Any] | None = None) -> dict[str, Any] | None:
    params = parameters or {}
    report = physical or read_physical(params)
    if report.get("kerf") != "PASS" or report.get("measured_bar_mm") is None:
        return None
    row = {
        "at": now_iso(),
        "machine": str(params.get("machine") or "payas_workshop"),
        "material": str(params.get("material") or "poplar_3mm"),
        "measured_bar_mm": report.get("measured_bar_mm"),
        "nominal_bar_mm": report.get("nominal_bar_mm") or NOMINAL_BAR_MM,
        "burn": report.get("suggested_burn"),
        "note": (report.get("notes") or {}).get("kerf"),
    }
    rows = [r for r in _load() if not (r.get("machine") == row["machine"] and r.get("material") == row["material"])]
    rows.append(row)
    write_json("calibrations.json", rows)
    return row


def latest_calibration(machine: str, material: str) -> dict[str, Any] | None:
    for row in reversed(_load()):
        if row.get("machine") == machine and row.get("material") == material:
            return row
    return None


def apply_stored_burn(parameters: dict[str, Any] | None) -> dict[str, Any]:
    params = dict(parameters or {})
    if params.get("measured_bar_mm") not in (None, ""):
        return params
    hit = latest_calibration(str(params.get("machine") or "payas_workshop"), str(params.get("material") or "poplar_3mm"))
    if hit and hit.get("burn"):
        params["burn"] = hit["burn"]
        params["calibration"] = hit
    return params


def list_calibrations() -> list[dict[str, Any]]:
    return _load()
