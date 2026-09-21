"""Human-attested physical tests. Software never invents a PASS."""

from __future__ import annotations

from typing import Any

from boxes_adapter import PAYAS_DEFAULTS

PASS = "PASS"
NOT_VERIFIED = "NOT_VERIFIED"
NA = "N/A"
FAIL = "FAIL"

NOMINAL_BAR_MM = 100.0
BURN_LO = 0.05
BURN_HI = 0.60


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy_pass(value: Any) -> bool:
    if value is True:
        return True
    text = str(value or "").strip().lower()
    return text in {"pass", "passed", "verified", "ok", "yes", "true", "1", "done"}


def _na(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"n/a", "na", "none", "no_moving", "stationary", "no_use", "unpowered"}


def read_physical(parameters: dict[str, Any] | None, *, moving: bool = False, powered: bool = False) -> dict[str, Any]:
    params = parameters or {}
    nested = params.get("physical") if isinstance(params.get("physical"), dict) else {}
    measured = _num(
        params.get("measured_bar_mm")
        or params.get("measured_100mm")
        or nested.get("measured_bar_mm")
        or nested.get("bar_mm")
    )
    nominal = _num(params.get("nominal_bar_mm") or nested.get("nominal_bar_mm")) or NOMINAL_BAR_MM
    kerf = NOT_VERIFIED
    kerf_note = "cut the 100 mm coupon bar and pass measured_bar_mm"
    if measured is not None:
        if 96.0 <= measured <= 104.0:
            kerf = PASS
            kerf_note = f"human measured the {nominal:.0f} mm bar as {measured:.2f} mm"
        else:
            kerf = FAIL
            kerf_note = f"measured_bar_mm {measured:.2f} is outside 96–104 mm — re-cut the coupon"

    assembly = NOT_VERIFIED
    assembly_note = "dry-fit the prototype; pass physical_assembly=verified"
    raw_ass = params.get("physical_assembly") if "physical_assembly" in params else nested.get("assembly")
    if _truthy_pass(raw_ass):
        assembly = PASS
        assembly_note = "human verified physical assembly"
    elif raw_ass not in (None, ""):
        assembly = FAIL
        assembly_note = f"physical_assembly={raw_ass!r} is not verified"

    movement = NOT_VERIFIED
    movement_note = "spin/slide the moving part; pass movement_test=verified"
    raw_move = params.get("movement_test") if "movement_test" in params else nested.get("movement")
    if not moving and (raw_move in (None, "") or _na(raw_move)):
        movement = NA
        movement_note = "no moving part — movement not applicable"
    elif _truthy_pass(raw_move):
        movement = PASS
        movement_note = "human verified movement"
    elif _na(raw_move):
        movement = NA
        movement_note = "human marked movement N/A"
    elif raw_move not in (None, ""):
        movement = FAIL
        movement_note = f"movement_test={raw_move!r} is not verified"

    use = NOT_VERIFIED
    use_note = "after assembly, run the kit; pass use_test=verified"
    raw_use = params.get("use_test") if "use_test" in params else nested.get("use")
    if not powered and (raw_use in (None, "") or _na(raw_use)):
        use = NA
        use_note = "no powered function — use test not applicable"
    elif _truthy_pass(raw_use):
        use = PASS
        use_note = "human verified after-assembly use"
    elif _na(raw_use):
        use = NA
        use_note = "human marked use N/A"
    elif raw_use not in (None, ""):
        use = FAIL
        use_note = f"use_test={raw_use!r} is not verified"

    current = _num(params.get("burn")) or float(PAYAS_DEFAULTS["burn"])
    suggested = current
    if measured is not None and 96.0 <= measured <= 104.0:
        suggested = max(BURN_LO, min(BURN_HI, current + (nominal - measured) / 2.0))
        suggested = round(suggested, 3)

    production_ok = kerf == PASS and assembly == PASS and movement in {PASS, NA} and use in {PASS, NA}
    return {
        "kerf": kerf,
        "assembly": assembly,
        "movement": movement,
        "use": use,
        "engraving": NOT_VERIFIED,
        "notes": {"kerf": kerf_note, "assembly": assembly_note, "movement": movement_note, "use": use_note},
        "measured_bar_mm": measured,
        "nominal_bar_mm": nominal,
        "suggested_burn": suggested,
        "production_ok": production_ok,
    }


def resolve_burn(parameters: dict[str, Any] | None, *, moving: bool = False, powered: bool = False) -> tuple[float, dict[str, Any]]:
    """Use an explicit burn, or the coupon-derived suggestion. Never invent a measurement."""
    params = dict(parameters or {})
    report = read_physical(params, moving=moving, powered=powered)
    explicit = _num(params.get("burn"))
    if explicit is not None and BURN_LO <= explicit <= BURN_HI and "measured_bar_mm" not in params:
        return round(explicit, 3), report
    return report["suggested_burn"], report
