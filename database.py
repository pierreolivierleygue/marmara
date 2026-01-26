import sqlite3
from pathlib import Path

DB_PATH = Path("vessel.db")

def init_db_vessel(db_path = DB_PATH):
    """Ensure the SQLite database exists with the expected schema."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vessels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mmsi INTEGER,
            imo INTEGER,
            name TEXT,
            type TEXT,
            flag TEXT,
            a REAL,
            b REAL,
            c REAL,
            d REAL,
            lat REAL,
            lng REAL,
            cog REAL,
            sog REAL,
            rot REAL,
            hdt REAL,
            dest TEXT,
            eta TEXT,
            ts TEXT,
            status INTEGER
        )
        """
    )
    conn.commit()
    return conn


def store_vessels(conn, vessels):
    """Store each vessel status"""
    inserted = 0
    with conn:
        cursor = conn.cursor()
        for vessel in vessels or []:
            payload = {
                "mmsi": vessel.get("mmsi"),
                "imo": vessel.get("imo"),
                "name": vessel.get("name"),
                "type": vessel.get("type"),
                "flag": vessel.get("flag"),
                "a": vessel.get("a"),
                "b": vessel.get("b"),
                "c": vessel.get("c"),
                "d": vessel.get("d"),
                "lat": vessel.get("lat"),
                "lng": vessel.get("lng"),
                "cog": vessel.get("cog"),
                "sog": vessel.get("sog"),
                "rot": vessel.get("rot"),
                "hdt": vessel.get("hdt"),
                "dest": vessel.get("dest"),
                "eta": vessel.get("eta"),
                "ts": vessel.get("ts"),
                "status": vessel.get("status"),
            }
            cursor.execute(
                """
                INSERT INTO vessels (
                    mmsi,
                    imo,
                    name,
                    type,
                    flag,
                    a,
                    b,
                    c,
                    d,
                    lat,
                    lng,
                    cog,
                    sog,
                    rot,
                    hdt,
                    dest,
                    eta,
                    ts,
                    status
                )
                VALUES (
                    :mmsi, :imo, :name, :type, :flag,
                    :a, :b, :c, :d, :lat, :lng,
                    :cog, :sog, :rot, :hdt, :dest,
                    :eta, :ts, :status
                )
                """,
                payload,
            )
            inserted += cursor.rowcount
    return inserted

def init_db_port(db_path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ports (
            port_id TEXT PRIMARY KEY,
            name TEXT,
            country TEXT,
            un_locode TEXT,
            lat REAL,
            long REAL,
            berths INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS port_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vessel_mmsi INTEGER,
            vessel_imo INTEGER,
            vessel_name TEXT,
            vessel_type TEXT,
            vessel_size_class TEXT,
            vessel_length REAL,
            vessel_width REAL,
            vessel_draft REAL,
            reference_ts TEXT,
            port_id TEXT NOT NULL,
            port_name TEXT,
            port_un_locode TEXT,
            port_country TEXT,
            port_lat REAL,
            port_long REAL
        )
        """
    )
    conn.commit()
    return conn


def store_ports(conn, ports):
    inserted = 0
    with conn:
        cursor = conn.cursor()
        for port in ports or []:
            payload = {
                "port_id": port.get("port_id"),
                "name": port.get("name"),
                "country": port.get("country"),
                "un_locode": port.get("un_locode"),
                "lat": port.get("lat"),
                "long": port.get("long"),
                "berths": port.get("berths"),
            }
            cursor.execute(
                """
                INSERT INTO ports (
                    port_id,
                    name,
                    country,
                    un_locode,
                    lat,
                    long,
                    berths
                )
                VALUES (
                    :port_id,
                    :name,
                    :country,
                    :un_locode,
                    :lat,
                    :long,
                    :berths
                )
                """,
                payload,
            )
            inserted += cursor.rowcount
    return inserted



__all__ = ["DB_PATH", "init_db", "store_vessels"]
