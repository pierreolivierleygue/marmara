import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Tuple, Dict


from database import DB_PATH

LOCAL_TZ = timezone(timedelta(hours=3))
# Variables de détection (port & entry)
MIN_SOG_KTS = 1.0
DIRECTION_TOLERANCE_DEG = 45
TRANSIT_PORTS = {"TRECE", "TRCKZ", "TRGEL", "TRIST"}

def fetch_positions_by_vessel(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(
            """
            SELECT mmsi, ts, lat, lng
            FROM vessels
            WHERE mmsi IS NOT NULL AND lat IS NOT NULL AND lng IS NOT NULL
            ORDER BY mmsi, ts
            """
        ).fetchall()
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["mmsi"]].append((row["ts"], row["lat"], row["lng"]))
    return grouped


def fetch_motion_tracks(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(
            """
            SELECT mmsi, ts, lat, lng, sog, cog
            FROM vessels
            WHERE mmsi IS NOT NULL AND lat IS NOT NULL AND lng IS NOT NULL
            ORDER BY mmsi, ts
            """
        ).fetchall()
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["mmsi"]].append(row)
    return grouped



def port_volume():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(
            """
            SELECT
                port_id,
                port_name,
                port_un_locode,
                COUNT(DISTINCT vessel_mmsi) AS vessel_count
            FROM port_visits
            GROUP BY port_id, port_name, port_un_locode
            ORDER BY vessel_count DESC
            """
        ).fetchall()
    return [
        {
            "port_id": row["port_id"],
            "name": row["port_name"],
            "un_locode": row["port_un_locode"],
            "vessel_count": row["vessel_count"],
        }
        for row in rows
    ]

def port_volume_by_cat():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(
            """
            SELECT
                port_id,
                port_name,
                port_un_locode,
                vessel_type,
                vessel_size_class,
                COUNT(DISTINCT vessel_mmsi) AS vessel_count
            FROM port_visits
            GROUP BY port_id, port_name, port_un_locode, vessel_type, vessel_size_class
            ORDER BY port_id
            """
        ).fetchall()

    summary = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        port_key = row["port_id"]
        vessel_type = row["vessel_type"] or "unknown"
        size_class = row["vessel_size_class"] or "unspecified"
        summary[port_key][vessel_type][size_class] = row["vessel_count"]
    return summary

def port_avg_vessel_size():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(
            """
            SELECT port_id, vessel_size_class, COUNT(*) AS samples
            FROM port_visits
            WHERE vessel_size_class IS NOT NULL
            GROUP BY port_id, vessel_size_class
            """
        ).fetchall()

    totals = defaultdict(int)
    counts = defaultdict(lambda: defaultdict(int))
    for row in rows:
        port_id = row["port_id"]
        size_class = row["vessel_size_class"]
        value = row["samples"]
        counts[port_id][size_class] += value
        totals[port_id] += value

    ratios = {}
    for port_id, size_counts in counts.items():
        total = totals[port_id]
        ratios[port_id] = {
            size_class: size_counts[size_class] / total if total else 0
            for size_class in size_counts
        }
    return ratios



@dataclass(frozen=True)
class BorderZone:
    name: str
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float
    entry_vector: Tuple[int, int]
    exit_vector: Tuple[int, int]
    entry_heading: float
    exit_heading: float

# Variables de définition des detroits
BORDER_ZONES: Dict[str, BorderZone] = {
    "sud": BorderZone(
        name="sud",
        lon_min=26.286530327448702,
        lon_max=26.760456950038616,
        lat_min=40.002124259750644,
        lat_max=40.40694872068113,
        entry_vector=(1, -1),
        exit_vector=(-1, 1),
        entry_heading=42.5266970882152,
        exit_heading=(42.5266970882152 + 180) % 360,
    ),
    "nord": BorderZone(
        name="nord",
        lon_min=28.99868259119853,
        lon_max=29.227864721743117,
        lat_min=41.05879544639964,
        lat_max=41.233884553525996,
        entry_vector=(-1, -1),
        exit_vector=(1, 1),
        entry_heading=18.487652578252778,
        exit_heading=(18.487652578252778 + 180) % 360,
    ),
}


def _parse_timestamp(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _point_in_zone(lat, lng, zone):
    return zone.lat_min <= lat <= zone.lat_max and zone.lon_min <= lng <= zone.lon_max


def _heading_diff(h1, h2):
    diff = (h1 - h2 + 180) % 360 - 180
    return abs(diff)


def _classify_direction(zone: BorderZone, cog):
    if cog is None:
        return None
    entry_diff = _heading_diff(cog, zone.entry_heading)
    if entry_diff <= DIRECTION_TOLERANCE_DEG:
        return "entry"
    exit_diff = _heading_diff(cog, zone.exit_heading)
    if exit_diff <= DIRECTION_TOLERANCE_DEG:
        return "exit"
    return None


def detect_border_passages(zone_key, db_path=DB_PATH, verbose=False):
    zone = BORDER_ZONES[zone_key]
    tracks = fetch_motion_tracks(db_path=db_path)
    passages = []
    total_in_zone = 0
    kept = 0

    for mmsi, fixes in tracks.items():
        for idx in range(len(fixes) - 1):
            current = fixes[idx]
            ts, lat, lng = current["ts"], current["lat"], current["lng"]
            if not _point_in_zone(lat, lng, zone):
                continue
            total_in_zone += 1
            sog = current["sog"] or 0
            if sog <= MIN_SOG_KTS:
                continue
            direction = _classify_direction(zone, current["cog"])
            if not direction:
                continue
            kept += 1
            next_fix = fixes[idx + 1]
            passages.append(
                {
                    "vessel_mmsi": mmsi,
                    "timestamp": ts,
                    "next_timestamp": next_fix["ts"],
                    "zone": zone.name,
                    "direction": direction,
                    "current_position": (lat, lng),
                    "next_position": (next_fix["lat"], next_fix["lng"]),
                }
            )
    if verbose:
        print(f"[{zone.name}] points in zone: {total_in_zone}, kept after direction check: {kept}")
    return passages


def detect_all_border_passages(db_path=DB_PATH, verbose=False):
    return {
        zone_key: detect_border_passages(zone_key, db_path=db_path, verbose=verbose)
        for zone_key in BORDER_ZONES
    }


def destination_stats(lag_hours=24, db_path=DB_PATH):
    passages = detect_all_border_passages(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    stats = {zone: defaultdict(int) for zone in passages}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lag_hours)
    entries_by_vessel = defaultdict(list)
    for zone_name, entries in passages.items():
        for entry in entries:
            if entry["direction"] != "entry":
                continue
            entry_ts = _parse_timestamp(entry["timestamp"])
            if not entry_ts or entry_ts > cutoff:
                continue
            entries_by_vessel[entry["vessel_mmsi"]].append({"zone": zone_name, "ts": entry_ts})
    if not entries_by_vessel:
        conn.close()
        return stats
    vessel_ids = list(entries_by_vessel.keys())
    placeholders = ",".join("?" for _ in vessel_ids)
    try:
        port_rows = conn.execute(
            f"""
            SELECT vessel_mmsi, port_un_locode, reference_ts
            FROM port_visits
            WHERE vessel_mmsi IN ({placeholders})
            """,
            tuple(vessel_ids),
        ).fetchall()
    finally:
        conn.close()

    visits_by_vessel = defaultdict(list)
    for row in port_rows:
        ts = _parse_timestamp(row["reference_ts"])
        if not ts:
            continue
        visits_by_vessel[row["vessel_mmsi"]].append(
            {"ts": ts, "dest": row["port_un_locode"] or "UNKNOWN_PORT"}
        )
    for visits in visits_by_vessel.values():
        visits.sort(key=lambda r: r["ts"])

    exits_by_vessel = defaultdict(list)
    for zone_name, entries in passages.items():
        for event in entries:
            if event["direction"] != "exit":
                continue
            ts = _parse_timestamp(event["timestamp"])
            if not ts:
                continue
            exits_by_vessel[event["vessel_mmsi"]].append({"ts": ts, "zone": zone_name})
    for exits in exits_by_vessel.values():
        exits.sort(key=lambda r: r["ts"])

    for vessel_id, entries in entries_by_vessel.items():
        entries.sort(key=lambda e: e["ts"])
        vessel_visits = visits_by_vessel.get(vessel_id, [])
        vessel_exits = exits_by_vessel.get(vessel_id, [])

        for idx, entry_info in enumerate(entries):
            entry_ts = entry_info["ts"]
            entry_zone = entry_info["zone"]
            next_entry_ts = entries[idx + 1]["ts"] if idx + 1 < len(entries) else None
            visit_candidates = [
                v for v in vessel_visits
                if v["ts"] > entry_ts and (next_entry_ts is None or v["ts"] < next_entry_ts)
            ]
            visit = visit_candidates[0] if visit_candidates else None
            exit_candidates = [
                e for e in vessel_exits
                if e["zone"] != entry_zone and e["ts"] > entry_ts and (next_entry_ts is None or e["ts"] < next_entry_ts)
            ]
            exit_ev = exit_candidates[0] if exit_candidates else None

            if visit:
                dest = visit["dest"]
                if dest in TRANSIT_PORTS and exit_ev and exit_ev["ts"] > visit["ts"]:
                    stats[entry_zone][f"exit_{exit_ev['zone']}"] += 1
                else:
                    stats[entry_zone][f"port_{dest}"] += 1
            elif exit_ev:
                stats[entry_zone][f"exit_{exit_ev['zone']}"] += 1
            else:
                stats[entry_zone]["unknown"] += 1

    return stats


def destination_breakdown(lag_hours=24, db_path=DB_PATH):
    stats = destination_stats(lag_hours=lag_hours, db_path=db_path)
    aggregated = defaultdict(int)
    for zone_stats in stats.values():
        for label, count in zone_stats.items():
            aggregated[label] += count
    return aggregated


def taille_bateau_nord_sud(db_path=DB_PATH):
    passages = detect_all_border_passages(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    size_stats = {zone: defaultdict(int) for zone in passages}

    try:
        for zone_name, entries in passages.items():
            vessel_ids = [entry["vessel_mmsi"] for entry in entries if entry["direction"] == "entry"]
            if not vessel_ids:
                continue
            placeholders = ",".join("?" for _ in vessel_ids)
            rows = conn.execute(
                f"""
                SELECT vessel_mmsi, vessel_size_class
                FROM port_visits
                WHERE vessel_mmsi IN ({placeholders})
                """,
                tuple(vessel_ids),
            ).fetchall()

            for row in rows:
                size_class = row["vessel_size_class"] or "unspecified"
                size_stats[zone_name][size_class] += 1
    finally:
        conn.close()

    return size_stats


def gate_entry_volume(zone_key, db_path=DB_PATH, duration_hours=24, shift_hours=4):
    entries = detect_border_passages(zone_key, db_path=db_path)
    entry_times = []
    for entry in entries:
        if entry["direction"] != "entry":
            continue
        timestamp = _parse_timestamp(entry["timestamp"])
        if not timestamp:
            continue
        entry_times.append(timestamp.astimezone(LOCAL_TZ))
    if entry_times:
        span_seconds = (max(entry_times) - min(entry_times)).total_seconds()
        span_days = max(1.0, span_seconds / 86400.0)
    else:
        span_days = 1.0

    total_bins = int(duration_hours / shift_hours)
    counts = [0] * total_bins

    for ts in entry_times:
        hour = ts.hour
        idx = min(total_bins - 1, hour // shift_hours)
        counts[idx] += 1
    counts = [c / span_days for c in counts]

    labels = []
    for i in range(total_bins):
        start_hour = i * shift_hours
        end_hour = start_hour + shift_hours
        labels.append(f"{start_hour:02d}:00 - {end_hour:02d}:00")

    return {
        "zone": zone_key,
        "labels": labels,
        "counts": counts,
        "shift_hours": shift_hours,
        "span_days": span_days,
    }


def gate_exit_volume(zone_key, db_path=DB_PATH, duration_hours=24, shift_hours=4):
    entries = detect_border_passages(zone_key, db_path=db_path)
    exit_times = []
    for event in entries:
        if event["direction"] != "exit":
            continue
        timestamp = _parse_timestamp(event["timestamp"])
        if not timestamp:
            continue
        exit_times.append(timestamp.astimezone(LOCAL_TZ))

    if exit_times:
        span_seconds = (max(exit_times) - min(exit_times)).total_seconds()
        span_days = max(1.0, span_seconds / 86400.0)
    else:
        span_days = 1.0

    total_bins = int(duration_hours / shift_hours)
    counts = [0] * total_bins

    for ts in exit_times:
        hour = ts.hour
        idx = min(total_bins - 1, hour // shift_hours)
        counts[idx] += 1

    counts = [c / span_days for c in counts]

    labels = []
    for i in range(total_bins):
        start_hour = i * shift_hours
        end_hour = start_hour + shift_hours
        labels.append(f"{start_hour:02d}:00 - {end_hour:02d}:00")

    return {
        "zone": zone_key,
        "labels": labels,
        "counts": counts,
        "shift_hours": shift_hours,
        "span_days": span_days,
    }


def gate_category_distribution(zone_key, db_path=DB_PATH):
    passages = detect_border_passages(zone_key, db_path=db_path)
    category_counts = defaultdict(int)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        vessel_ids = {entry["vessel_mmsi"] for entry in passages if entry["direction"] == "entry"}
        if not vessel_ids:
            return category_counts
        placeholders = ",".join("?" for _ in vessel_ids)
        rows = conn.execute(
            f"""
            SELECT vessel_mmsi, vessel_type
            FROM port_visits
            WHERE vessel_mmsi IN ({placeholders})
            """,
            tuple(vessel_ids),
        ).fetchall()
        type_map = {row["vessel_mmsi"]: row["vessel_type"] or "unknown" for row in rows}
    finally:
        conn.close()

    for entry in passages:
        if entry["direction"] != "entry":
            continue
        vessel_type = type_map.get(entry["vessel_mmsi"], "unknown")
        category_counts[vessel_type] += 1
    return category_counts


def gate_size_distribution(zone_key, db_path=DB_PATH):
    passages = detect_border_passages(zone_key, db_path=db_path)
    size_counts = defaultdict(int)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        vessel_ids = {entry["vessel_mmsi"] for entry in passages if entry["direction"] == "entry"}
        if not vessel_ids:
            return size_counts
        placeholders = ",".join("?" for _ in vessel_ids)
        rows = conn.execute(
            f"""
            SELECT vessel_mmsi, vessel_size_class
            FROM port_visits
            WHERE vessel_mmsi IN ({placeholders})
            """,
            tuple(vessel_ids),
        ).fetchall()
        size_map = {row["vessel_mmsi"]: row["vessel_size_class"] or "unspecified" for row in rows}
    finally:
        conn.close()

    for entry in passages:
        if entry["direction"] != "entry":
            continue
        size_label = size_map.get(entry["vessel_mmsi"], "unspecified")
        size_counts[size_label] += 1
    return size_counts
