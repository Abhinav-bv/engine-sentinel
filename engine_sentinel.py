"""Explainable maintenance triage for illustrative engine telemetry.

Standard-library only. This is a portfolio prototype, not a diagnostic device.
"""

from __future__ import annotations

import argparse
import csv
import html
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


FIELDS = ("engine_id", "timestamp_utc", "rpm", "coolant_temp_c", "oil_pressure_kpa", "battery_v", "fault_code")
NUMERIC = ("rpm", "coolant_temp_c", "oil_pressure_kpa", "battery_v")
SCENARIOS = {
    "ENG-101": "stable",
    "ENG-102": "cooling trend",
    "ENG-103": "oil pressure trend",
    "ENG-104": "charging trend",
    "ENG-105": "missing telemetry",
    "ENG-106": "short temperature spike",
}


def make_demo(path: Path) -> None:
    """Write repeatable synthetic data. No company or vehicle data is used."""
    rng = random.Random(1027)
    start = datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for engine in SCENARIOS:
            for i in range(96):
                rpm = 1450 + rng.randint(-90, 90)
                coolant = 88 + rng.uniform(-1.4, 1.4)
                oil = 360 + rng.uniform(-12, 12)
                battery = 13.9 + rng.uniform(-0.08, 0.08)
                fault = ""
                if engine == "ENG-102" and i >= 64:
                    coolant += (i - 63) * 0.34
                    if i >= 84:
                        fault = "COOLING_ALERT"
                if engine == "ENG-103" and i >= 60:
                    oil -= (i - 59) * 1.65
                    if i >= 86:
                        fault = "OIL_PRESSURE_ALERT"
                if engine == "ENG-104" and i >= 64:
                    battery -= (i - 63) * 0.037
                if engine == "ENG-106" and i == 91:
                    coolant = 108
                if engine == "ENG-105" and i >= 68:
                    coolant = None if i % 2 == 0 else coolant
                    oil = None if i % 3 else oil
                    battery = None if i % 4 else battery
                writer.writerow({
                    "engine_id": engine,
                    "timestamp_utc": (start + timedelta(minutes=15 * i)).isoformat().replace("+00:00", "Z"),
                    "rpm": round(rpm),
                    "coolant_temp_c": "" if coolant is None else round(coolant, 2),
                    "oil_pressure_kpa": "" if oil is None else round(oil, 2),
                    "battery_v": "" if battery is None else round(battery, 3),
                    "fault_code": fault,
                })


def load_csv(path: Path) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = set(FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        for line, row in enumerate(reader, 2):
            engine = row["engine_id"].strip()
            if not engine:
                raise ValueError(f"Line {line}: empty engine_id")
            try:
                stamp = datetime.fromisoformat(row["timestamp_utc"].strip().replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    raise ValueError("timestamp needs timezone")
                values = {key: (float(row[key]) if row[key] and row[key].strip() else None) for key in NUMERIC}
                if any(value is not None and not math.isfinite(value) for value in values.values()):
                    raise ValueError("numeric fields must be finite")
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Line {line}: {exc}") from exc
            groups[engine].append({"timestamp": stamp.astimezone(timezone.utc), **values, "fault_code": row["fault_code"].strip()})
    for rows in groups.values():
        rows.sort(key=lambda item: item["timestamp"])
    return dict(groups)


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def analyze_engine(engine: str, rows: list[dict]) -> dict:
    recent = rows[-12:]
    baseline = rows[:24]
    valid = sum(row[key] is not None for row in recent for key in NUMERIC)
    completeness = valid / (len(recent) * len(NUMERIC))
    reasons = []
    score = 0

    # Require repeated abnormal values: a single spike is not enough.
    checks = (
        ("coolant_temp_c", lambda x: x >= 96, "sustained high coolant temperature", 35),
        ("oil_pressure_kpa", lambda x: x <= 320, "sustained low oil pressure", 40),
        ("battery_v", lambda x: x <= 13.2, "sustained low charging voltage", 25),
    )
    for key, predicate, label, points in checks:
        known = [row[key] for row in recent if row[key] is not None]
        if len(known) >= 8 and sum(predicate(value) for value in known) >= 8:
            score += points
            reasons.append(label)

    trends = (
        ("coolant_temp_c", 5, 18, "coolant temperature rose from baseline"),
        ("oil_pressure_kpa", -30, 18, "oil pressure fell from baseline"),
        ("battery_v", -0.5, 15, "charging voltage fell from baseline"),
    )
    for key, threshold, points, label in trends:
        old = average([row[key] for row in baseline if row[key] is not None])
        new = average([row[key] for row in recent if row[key] is not None])
        if old is not None and new is not None and (new - old >= threshold if threshold > 0 else new - old <= threshold):
            score += points
            reasons.append(f"{label} ({new - old:+.1f})")

    fault_count = sum(bool(row["fault_code"]) for row in recent)
    if fault_count >= 3:
        score += 25
        reasons.append(f"fault code present in {fault_count}/12 recent samples")

    if len(rows) < 24 or completeness < 0.75:
        status = "INSUFFICIENT DATA"
        reasons.insert(0, "telemetry coverage is too low for a reliable triage decision")
    elif score >= 50:
        status = "SERVICE SOON"
    elif score >= 20:
        status = "WATCH"
    else:
        status = "NORMAL"
        reasons.append("no sustained threshold breach or material trend detected")
    return {"engine": engine, "status": status, "score": min(score, 100), "coverage": completeness,
            "samples": len(rows), "reasons": reasons, "rows": rows, "latest": rows[-1]["timestamp"]}


def sparkline(values: list[float | None], color: str) -> str:
    known = [value for value in values if value is not None]
    if len(known) < 2:
        return '<span class="muted">insufficient data</span>'
    low, high = min(known), max(known)
    span = high - low or 1
    points = []
    for i, value in enumerate(values):
        if value is not None:
            points.append(f"{i * 220 / max(len(values)-1,1):.1f},{35-(value-low)*30/span:.1f}")
    return f'<svg viewBox="0 0 220 40" role="img" aria-label="Recent sensor trend"><polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def render(results: list[dict], source: Path) -> str:
    cards = []
    colors = {"SERVICE SOON": "red", "WATCH": "amber", "NORMAL": "green", "INSUFFICIENT DATA": "gray"}
    for item in results:
        rows = item["rows"][-24:]
        charts = "".join(
            f'<div class="sensor"><span>{label}</span>{sparkline([row[key] for row in rows], color)}'
            f'<small>{html.escape(str(next((round(row[key], 1) for row in reversed(rows) if row[key] is not None), "—")))}</small></div>'
            for key, label, color in (("coolant_temp_c", "Coolant °C", "#f97354"),
                                      ("oil_pressure_kpa", "Oil pressure kPa", "#5d9bf5"),
                                      ("battery_v", "Battery V", "#b887f2"))
        )
        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in item["reasons"])
        cards.append(f'<article class="card {colors[item["status"]]}"><div class="cardhead"><h2>{html.escape(item["engine"])}</h2>'
                     f'<span class="badge">{item["status"]}</span></div><p class="metric">Triage score <strong>{item["score"]}</strong> · '
                     f'coverage <strong>{item["coverage"]:.0%}</strong> · {item["samples"]} samples</p>'
                     f'<div class="charts">{charts}</div><h3>Why this status</h3><ul>{reasons}</ul></article>')
    counts = {status: sum(item["status"] == status for item in results) for status in colors}
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Engine Sentinel | Maintenance triage</title><style>
:root{{font-family:Inter,Segoe UI,Arial,sans-serif;color:#e8edf6;background:#101723}}*{{box-sizing:border-box}}body{{margin:0}}
header{{padding:42px max(24px,calc((100vw - 1100px)/2));background:linear-gradient(120deg,#19283d,#14202e);border-bottom:1px solid #304158}}
.eyebrow{{color:#7dd3be;letter-spacing:.16em;text-transform:uppercase;font-size:12px;font-weight:700}}h1{{font-size:clamp(32px,5vw,54px);margin:12px 0}}
header p{{color:#b7c5d5;line-height:1.5;max-width:760px}}main{{max-width:1100px;margin:30px auto;padding:0 20px}}
.summary{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}}.summary span{{background:#1d2a3a;border:1px solid #34465d;padding:11px 16px;border-radius:12px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}}.card{{background:#1a2636;border:1px solid #33475e;border-radius:18px;padding:22px}}
.cardhead{{display:flex;align-items:center;justify-content:space-between;gap:8px}}h2{{margin:0;font-size:22px}}.badge{{font-size:11px;font-weight:800;letter-spacing:.06em;padding:8px;border-radius:8px;background:#263b47}}
.red .badge{{background:#713339;color:#ffd5d8}}.amber .badge{{background:#675323;color:#ffe3a4}}.green .badge{{background:#245749;color:#b9f4dd}}.gray .badge{{background:#465163;color:#e0e6ef}}
.metric{{font-size:13px;color:#aebdd0}}.charts{{border-top:1px solid #33475e;border-bottom:1px solid #33475e;padding:10px 0}}
.sensor{{display:grid;grid-template-columns:105px 1fr 42px;align-items:center;gap:10px;font-size:12px;color:#bdcbe0}}svg{{width:100%;height:42px}}small{{text-align:right}}
h3{{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#8bd8c4}}li{{margin:7px 0;line-height:1.4}}ul{{padding-left:19px}}.note{{font-size:13px;color:#aebdd0;line-height:1.5;margin:30px 0}}
</style></head><body><header><div class="eyebrow">Abhinav's portfolio lab · synthetic demo</div><h1>Engine Sentinel</h1>
<p>Quiet signals. Clear calls. A maintenance triage experiment that shows why an engine is flagged and when the data is too thin to trust.</p></header>
<main><div class="summary"><span>Service soon: <b>{counts["SERVICE SOON"]}</b></span><span>Watch: <b>{counts["WATCH"]}</b></span><span>Normal: <b>{counts["NORMAL"]}</b></span><span>Insufficient data: <b>{counts["INSUFFICIENT DATA"]}</b></span></div>
<div class="grid">{"".join(cards)}</div><p class="note">Source: {html.escape(source.name)}. Scores and thresholds are illustrative and are not validated for real engines. Do not use this report for vehicle operation or maintenance decisions.</p></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="CSV with engine_id, timestamp_utc, rpm, coolant_temp_c, oil_pressure_kpa, battery_v, fault_code")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "report.html")
    args = parser.parse_args()
    source = args.input or Path(__file__).parent / "data" / "synthetic_fleet.csv"
    if args.input is None:
        make_demo(source)
    groups = load_csv(source)
    if not groups:
        parser.error("input CSV contains no data rows")
    results = [analyze_engine(engine, rows) for engine, rows in groups.items()]
    results.sort(key=lambda item: ({"SERVICE SOON": 0, "WATCH": 1, "INSUFFICIENT DATA": 2, "NORMAL": 3}[item["status"]], -item["score"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(results, source), encoding="utf-8")
    for item in results:
        print(f'{item["engine"]:8} {item["status"]:18} score={item["score"]:3} coverage={item["coverage"]:.0%}')
    print(f"Report: {args.output.resolve()}")


if __name__ == "__main__":
    main()

