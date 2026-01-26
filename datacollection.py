import time
from datetime import datetime, timezone
import requests
from database import DB_PATH, init_db_vessel, init_db_port, store_vessels, store_ports
import sqlite3
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2
from typing import List, Tuple
from file import api_key # Clé unique à renseigner pour la récolte de données

DB_PATH = Path("vessel.db")
api_url_port = "https://api.marinesia.com/api/v1/port/nearby"
api_url = "https://api.marinesia.com/api/v1/vessel/nearby"

# Délimitation de la mer de Marmara (adaptant la definition de l'Organisation Hydrographique Internationale)
lat_min = 40.005979740179384
lat_max = 41.23724497024557
long_min = 26.169340151772246
long_max = 29.956654912552665

def current_vessel_by_area():
    params = {
        "key": api_key,
        "lat_min": lat_min,
        "lat_max": lat_max,
        "long_min": long_min,
        "long_max": long_max,
    }
    response = requests.get(api_url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()

def veille_de_navigation(interval_minutes=15):
    """Active l'API chaque `interval_minutes` pour stocker les data."""
    conn = init_db_vessel(DB_PATH)
    try:
        while True:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            payload = current_vessel_by_area()
            vessels = payload.get("data") if isinstance(payload, dict) else payload
            inserted = store_vessels(conn, vessels or [])
            print(f"{inserted} vessel positions stored. Database: {DB_PATH.resolve()}. Time: {timestamp}")
            time.sleep(interval_minutes * 60)
    finally:
        conn.close()


# Classification des bateaux par taille
SIZE_BUCKETS = (
    ("<50m", 15, 50),
    ("50-100m", 50, 100),
    ("100-150m", 100, 150),
    ("150-200m", 150, 200),
    (">200m", 200, float("inf")),
)

# Aire de fonctionnement de chaque port 
PORT_POLYGONS: dict[str, List[Tuple[float, float]]] = {
    "TRATV": [
        (29.483374900795923, 40.717605322311535),
        (29.48329122734398, 40.717602206708044),
        (29.483208359736427, 40.717592889903386),
        (29.48312709605604, 40.71757746162607),
        (29.483048218937135, 40.71755607046303),
        (29.482972488027595, 40.717528922428485),
        (29.48290063267233, 40.71749627897971),
        (29.482833344888725, 40.71745845449878),
        (29.482771272701733, 40.717415813264616),
        (29.482715013902727, 40.71736876594447),
        (29.482665110292416, 40.71731776563857),
        (29.482622042463028, 40.71726330351623),
        (29.482586225170284, 40.7172059040853),
        (29.482558003339417, 40.71714612014053),
        (29.482537648743993, 40.7170845274396),
        (29.482525357389225, 40.71702171915811),
        (29.482521247625183, 40.716958300176714),
        (29.48252535900782, 40.71689488125571),
        (29.482537651918978, 40.71683207315315),
        (29.482558007948793, 40.71677048074279),
        (29.482586231036898, 40.716710697189036),
        (29.482622049361442, 40.71665329823456),
        (29.48266511795752, 40.716598836655805),
        (29.48271502203996, 40.71654783693973),
        (29.482771280998378, 40.716500790232985),
        (29.482833353025956, 40.71645814961222),
        (29.48290064033743, 40.71642032572113),
        (29.48297249492601, 40.716387682815935),
        (29.483048224803756, 40.71636053525785),
        (29.483127100665413, 40.716339144485836),
        (29.483208362911423, 40.71632371649907),
        (29.483291228962575, 40.71631439987333),
        (29.483374900795923, 40.71631128433026),
        (29.483458572629267, 40.71631439987333),
        (29.48354143868042, 40.71632371649907),
        (29.483622700926432, 40.716339144485836),
        (29.483701576788086, 40.71636053525785),
        (29.483777306665836, 40.716387682815935),
        (29.483849161254412, 40.71642032572113),
        (29.483916448565882, 40.71645814961222),
        (29.48397852059346, 40.716500790232985),
        (29.48403477955188, 40.71654783693973),
        (29.484084683634325, 40.716598836655805),
        (29.4841277522304, 40.71665329823456),
        (29.48416357055494, 40.716710697189036),
        (29.484191793643053, 40.71677048074279),
        (29.48421214967286, 40.71683207315315),
        (29.48422444258402, 40.71689488125571),
        (29.484228553966663, 40.716958300176714),
        (29.48422444420262, 40.71702171915811),
        (29.484212152847853, 40.7170845274396),
        (29.484191798252425, 40.71714612014053),
        (29.484163576421558, 40.7172059040853),
        (29.48412775912881, 40.71726330351623),
        (29.48408469129943, 40.71731776563857),
        (29.48403478768911, 40.71736876594447),
        (29.48397852889011, 40.717415813264616),
        (29.483916456703117, 40.71745845449878),
        (29.483849168919516, 40.71749627897971),
        (29.48377731356425, 40.717528922428485),
        (29.483701582654703, 40.71755607046303),
        (29.4836227055358, 40.71757746162607),
        (29.483541441855415, 40.717592889903386),
        (29.483458574247866, 40.717602206708044),
        (29.483374900795923, 40.717605322311535),
    ],
    "TRIZT": [
        (29.709201753672033, 40.78061087452659),
        (29.754485232680906, 40.73498561517107),
        (29.797183716465042, 40.738412848639655),
        (29.741565539729407, 40.790343897522035),
    ],
    "TRGOK": [
        (29.83514915147495, 40.73076608192949),
        (29.834606253886307, 40.70261142139145),
        (29.91140470749056, 40.701855215211225),
        (29.90800715430251, 40.73343136949529),
    ],
    "TRDRC": [
        (29.94398023063937, 40.773731982115976),
        (29.828114585684773, 40.773731982115976),
        (29.828114585684773, 40.744472137737716),
        (29.94398023063937, 40.744472137737716),
    ],
    "TRGEB": [
        (29.504743035191808, 40.7793788155042),
        (29.504743035191808, 40.762316963233445),
        (29.589128905266932, 40.762316963233445),
        (29.589128905266932, 40.7793788155042),
    ],
    "TRTUZ": [
        (29.23950133928267, 40.892300848692344),
        (29.20373222430848, 40.86659293031471),
        (29.305232349396505, 40.77848851644089),
        (29.35644702242007, 40.82779280965596),
    ],
    "TRIST": [
        (28.988356905092587, 41.02256975626966),
        (28.744794298258938, 40.99647136598304),
        (28.750224506350662, 40.97257510464772),
        (28.809276730667136, 40.94643238298485),
        (28.994365194063732, 40.995119460043895),
    ],
    "TRMAR": [
        (27.871849497680415, 41.00788535958378),
        (27.871849497680415, 40.936398830072676),
        (28.023436071788723, 40.936398830072676),
        (28.023436071788723, 41.00788535958378),
    ],
    "TRTEK": [
        (27.47638582082783, 40.98196673811876),
        (27.47638582082783, 40.94408286979123),
        (27.591019935780196, 40.94408286979123),
        (27.591019935780196, 40.98196673811876),
    ],
    "TRSRL": [
        (27.748686953387022, 40.671618863328575),
        (27.51969279988458, 40.671618863328575),
        (27.51969279988458, 40.56641266090361),
        (27.748686953387022, 40.56641266090361),
    ],
    "TRGEL": [
        (26.6416208758327, 40.415065295482265),
        (26.6416208758327, 40.398972378904574),
        (26.69010473204969, 40.398972378904574),
        (26.69010473204969, 40.415065295482265),
    ],
    "TRECE": [
        (26.354691974436975, 40.18855129664979),
        (26.354691974436975, 40.179906905086625),
        (26.367285653800565, 40.179906905086625),
        (26.367285653800565, 40.18855129664979),
    ],
    "TRCKZ": [
        (26.409285567032327, 40.15604861591808),
        (26.39621787480695, 40.15604861591808),
        (26.39621787480695, 40.14435578572474),
        (26.409285567032327, 40.14435578572474),
    ],
    "TRIDS": [
        (27.08025789826013, 40.4524271002206),
        (27.08025789826013, 40.44702898109409),
        (27.088141686123436, 40.44702898109409),
        (27.088141686123436, 40.4524271002206),
    ],
    "TRBDM": [
        (27.917052854226313, 40.394122388240675),
        (27.917052854226313, 40.33514283098745),
        (28.033588388565306, 40.33514283098745),
        (28.033588388565306, 40.394122388240675),
    ],
    "TRMUD": [
        (28.87912349957611, 40.3923416386302),
        (28.85145727126738, 40.37906477170449),
        (28.923911938565567, 40.33737672715054),
        (28.940540321051486, 40.36061779639468),
    ],
    "TRGEM": [
        (29.074515254671468, 40.426173044701386),
        (29.074515254671468, 40.40740752560433),
        (29.15114537474662, 40.40740752560433),
        (29.15114537474662, 40.426173044701386),
    ],
}

def port_by_area():
    params = {
        "key": api_key,
        "lat_min": lat_min,
        "lat_max": lat_max,
        "long_min": long_min,
        "long_max": long_max,
    }
    response = requests.get(api_url_port, params=params, timeout=15)
    response.raise_for_status()
    return response.json()

def refresh_ports():
    payload = port_by_area()
    ports = payload.get("data") if isinstance(payload, dict) else payload
    conn = init_db_port(DB_PATH)
    inserted = store_ports(conn, ports)
    conn.close()
    return inserted


def classify_vessel_size(length_m):
    if length_m is None:
        return None
    for label, low, high in SIZE_BUCKETS:
        if low <= length_m < high:
            return label
    return SIZE_BUCKETS[-1][0]


def prepare_port_visit(vessel, port, reference_ts):
    length = vessel["a"] or vessel["b"]
    width = vessel["c"]
    draft = vessel["d"]
    return {
        "vessel_mmsi": vessel["mmsi"],
        "vessel_imo": vessel["imo"],
        "vessel_name": vessel["name"],
        "vessel_type": vessel["type"],
        "vessel_size_class": classify_vessel_size(length),
        "vessel_length": length,
        "vessel_width": width,
        "vessel_draft": draft,
        "reference_ts": reference_ts,
        "port_id": port["port_id"],
        "port_name": port["name"],
        "port_un_locode": port["un_locode"],
        "port_country": port["country"],
        "port_lat": port["lat"],
        "port_long": port["long"],
    }


def store_port_visits(conn, visits):
    inserted = 0
    with conn:
        cursor = conn.cursor()
        for visit in visits or []:
            cursor.execute(
                """
                INSERT INTO port_visits (
                    vessel_mmsi,
                    vessel_imo,
                    vessel_name,
                    vessel_type,
                    vessel_size_class,
                    vessel_length,
                    vessel_width,
                    vessel_draft,
                    reference_ts,
                    port_id,
                    port_name,
                    port_un_locode,
                    port_country,
                    port_lat,
                    port_long
                )
                VALUES (
                    :vessel_mmsi,
                    :vessel_imo,
                    :vessel_name,
                    :vessel_type,
                    :vessel_size_class,
                    :vessel_length,
                    :vessel_width,
                    :vessel_draft,
                    :reference_ts,
                    :port_id,
                    :port_name,
                    :port_un_locode,
                    :port_country,
                    :port_lat,
                    :port_long
                )
                """,
                visit,
            )
            inserted += cursor.rowcount
    return inserted


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def point_in_polygon(lat, lon, polygon):
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if ((y1 > lat) != (y2 > lat)) and (
            lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-12) + x1
        ):
            inside = not inside
    return inside


def detect_port_visits(db_path=DB_PATH):
    conn = init_db_port(db_path)
    conn.row_factory = sqlite3.Row
    inserted = 0
    try:
        conn.execute("DELETE FROM port_visits")
        conn.commit()
        ports = conn.execute("SELECT * FROM ports").fetchall()
        if not ports:
            return 0

        vessels = conn.execute(
            "SELECT * FROM vessels WHERE lat IS NOT NULL AND lng IS NOT NULL"
        ).fetchall()

        visits = []
        for vessel in vessels:
            for port in ports:
                locode = port["un_locode"]
                if locode in PORT_POLYGONS:
                    polygon = PORT_POLYGONS[locode]
                    if point_in_polygon(vessel["lat"], vessel["lng"], polygon):
                        visits.append(prepare_port_visit(vessel, port, vessel["ts"]))
                        break
                else:
                    radius_km = max(1.0, float(port["berths"] or 1))
                    distance = haversine_km(
                        vessel["lat"], vessel["lng"], port["lat"], port["long"]
                    )
                    if distance <= radius_km:
                        visits.append(prepare_port_visit(vessel, port, vessel["ts"]))
                        break

        if visits:
            inserted = store_port_visits(conn, visits)
        return inserted
    finally:
        conn.close()

if __name__ == "__main__":
    detect_port_visits()
    refresh_ports()
    veille_de_navigation()

