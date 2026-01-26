from collections import defaultdict
from pathlib import Path
from typing import Tuple
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from matplotlib.colors import LogNorm
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np

from analysis import (
    fetch_positions_by_vessel,
    port_volume,
    port_volume_by_cat,
    gate_entry_volume,
    gate_exit_volume,
    destination_breakdown,
    gate_category_distribution,
    gate_size_distribution,
)

### Heat Map
LatLng = Tuple[float, float]
Segment = Tuple[LatLng, LatLng]

# Couleurs utilisées pour les visuels
SIZE_CLASS_COLORS = {
    "<50m": "#2B78E2",
    "50-100m": "#225DB0",
    "100-150m": "#1E539C",
    "150-200m": "#15396B",
    ">200m": "#0F2D56",
    "unspecified": "#E5E7EB",
}


def colors_for_labels(labels):
    base_color = np.array([33, 90, 171]) / 255.0
    fallback = [base_color * f for f in np.linspace(0.4, 1.0, max(1, len(labels)))]
    colors = []
    fallback_iter = iter(fallback)
    for label in labels:
        colors.append(SIZE_CLASS_COLORS.get(label, next(fallback_iter)))
    return colors

def build_segments(positions, max_gap_hours=None):
    max_gap = None if max_gap_hours is None else max_gap_hours * 3600
    segments = []
    for fixes in positions.values():
        parsed = []
        for ts, lat, lon in fixes:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                lat = float(lat)
                lon = float(lon)
            except Exception:
                continue
            if lon > 180:
                lon -= 360
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            parsed.append((dt, lat, lon))

        parsed.sort(key=lambda x: x[0])

        for (dt1, lat1, lon1), (dt2, lat2, lon2) in zip(parsed, parsed[1:]):
            dt = (dt2 - dt1).total_seconds()
            if dt < 0:
                continue
            if max_gap is not None and dt > max_gap:
                continue
            segments.append(((lat1, lon1), (lat2, lon2)))

    return segments

def sample_segment_points(segments, samples_per_segment=25):
    lats = []
    lons = []
    for (lat1, lon1), (lat2, lon2) in segments:
        t_values = np.linspace(0, 1, samples_per_segment)
        lats.extend(lat1 + (lat2 - lat1) * t_values)
        lons.extend(lon1 + (lon2 - lon1) * t_values)
    return np.array(lats), np.array(lons)

def render_route_heatmap(output_path=Path("figures/routes.png"), max_gap_hours=10):
    positions = fetch_positions_by_vessel()
    segments = build_segments(positions, max_gap_hours=max_gap_hours)

    lon_min, lon_max = 26.0, 30.1
    lat_min, lat_max = 39.7, 41.6

    fig = plt.figure(figsize=(8, 5))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale("10m"), facecolor="white", edgecolor="none", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("10m"),  facecolor="white", edgecolor="none", zorder=0.1)

    lats, lons = sample_segment_points(segments)
    if lats.size > 0:
        grid_size = 400
        lat_edges = np.linspace(lat_min, lat_max, grid_size + 1)
        lon_edges = np.linspace(lon_min, lon_max, grid_size + 1)

        heatmap, _, _ = np.histogram2d(lats, lons, bins=[lat_edges, lon_edges])

        heatmap = np.ma.masked_less(heatmap, 1)
        vmax = heatmap.max() if heatmap.count() else 1

        mesh = ax.pcolormesh(
            lon_edges, lat_edges, heatmap,
            cmap="inferno",
            norm=LogNorm(vmin=1, vmax=vmax),
            shading="flat",
            transform=ccrs.PlateCarree(),
            alpha=0.85,
            linewidth=0,
            antialiased=False,
            zorder=1.5,
        )

    ax.coastlines(resolution="10m", linewidth=0.5, edgecolor="black", zorder=2)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Fréquence des routes dans la mer Marmara")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def render_top_ports_bar_chart(top_n=5, output_path=Path("figures/top_ports.png")):
    data = port_volume()
    top_ports = data[:top_n]
    labels = [entry["name"] or entry["un_locode"] or entry["port_id"] for entry in top_ports]
    counts = [entry["vessel_count"] for entry in top_ports]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, counts, color="#0B1F3B")
    ax.set_title(f"Les {len(top_ports)} ports les plus fréquentés")
    ax.set_ylabel("Nombre de navires distincts")
    ax.set_xlabel("Port")
    ax.set_xticklabels(labels, rotation=0, ha="center")

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="both", length=0)

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="both", length=0)

    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def render_top_grand_destinations(top_n=3, output_path=Path("figures/top_grand_ports.png")):
    data = port_volume_by_cat()
    port_info = {entry["port_id"]: entry for entry in port_volume()}
    grand_counts = defaultdict(int)
    for port_id, types_dict in data.items():
        for type_counts in types_dict.values():
            grand_counts[port_id] += type_counts.get("150-200m", 0)
            grand_counts[port_id] += type_counts.get(">200m", 0)

    top_entries = sorted(grand_counts.items(), key=lambda item: item[1], reverse=True)[:top_n]
    labels = []
    for port_id, _ in top_entries:
        info = port_info.get(port_id)
        labels.append(info["name"] if info and info["name"] else port_id)
    counts = [entry[1] for entry in top_entries]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, counts, color="#0B1F3B")
    ax.set_title(f"Les {len(top_entries)} destinations des navires >150m")
    ax.set_ylabel("Nombre de navires >150m")
    ax.set_xlabel("Port")
    ax.set_xticklabels(labels, rotation=0, ha="center")

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="both", length=0)

    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def render_category_pie_chart(output_path=Path("figures/category_pie.png")):
    data = port_volume_by_cat()
    port_info = {entry["port_id"]: entry for entry in port_volume()}
    category_counts = defaultdict(int)
    preferred_ports = defaultdict(lambda: ("", 0))

    for port_id, types_dict in data.items():
        for type_counts in types_dict.values():
            for size_class, count in type_counts.items():
                label = size_class or "unspecified"
                category_counts[label] += count
                info = port_info.get(port_id)
                name = (info["name"] or info["un_locode"] or port_id) if info else port_id
                if count > preferred_ports[label][1]:
                    preferred_ports[label] = (name, count)

    size_order = ["<50m", "50-100m", "100-150m", "150-200m", ">200m"]
    labels = [lbl for lbl in size_order if lbl in category_counts and lbl != "unspecified"]
    if not labels:
        labels = [lbl for lbl in category_counts.keys() if lbl != "unspecified"]
    missing = category_counts.get("unspecified", 0)
    counts = [category_counts[label] for label in labels]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))
    colors = colors_for_labels(labels)
    wedges, texts, autotexts = ax.pie(
        counts,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
        colors=colors,
    )
    ax.set_title("Répartition globale des catégories de navires")
    if missing:
        total = sum(counts) + missing
        missing_pct = 100 * missing / total if total else 0
        ax.text(0.5, -0.1, f"{missing_pct:.1f}% de données manquantes", ha="center", va="center", transform=ax.transAxes)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def render_gate_entry_chart(zone_key, output_path=None):
    data = gate_entry_volume(zone_key)
    zone_name = 'Bosphore'
    if zone_key == 'sud':
        zone_name = 'Dardanelles' 
    if output_path is None:
        output_path = Path(f"figures/entries/{zone_key}_entry_volume.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(range(len(data["counts"])), data["counts"], color="#0B1F3B")
    ax.set_xticks(range(len(data["labels"])))
    ax.set_xticklabels(data["labels"], rotation=0, ha="center", fontsize=8)
    ax.set_ylabel("Entrées (moyenne/jour)")
    ax.set_title(f"Entrées moyennes par créneau ({zone_name})")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def render_gate_exit_chart(zone_key, output_path=None):
    data = gate_exit_volume(zone_key)
    zone_name = 'Bosphore'
    if zone_key == 'sud':
        zone_name = 'Dardanelles'

    if output_path is None:
        output_path = Path(f"figures/exits/{zone_key}_exit_volume.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(range(len(data["counts"])), data["counts"], color="#0B1F3B")
    ax.set_xticks(range(len(data["labels"])))
    ax.set_xticklabels(data["labels"], rotation=0, ha="center", fontsize=8)
    ax.set_ylabel("Sorties (moyenne/jour)")
    ax.set_title(f"Sorties moyennes par créneau ({zone_name})")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def render_destination_breakdown_pie(
    lag_hours=2,
    include_unknown=True,
    output_path=Path("figures/destination_breakdown.png"),
):
    breakdown = destination_breakdown(lag_hours=lag_hours)
    if not include_unknown:
        breakdown.pop("unknown", None)
    if not breakdown:
        raise ValueError("Aucune donnée de destination disponible.")

    port_info = {entry["un_locode"] or entry["port_id"]: entry for entry in port_volume()}
    labels = []
    counts = []

    for key, count in sorted(breakdown.items(), key=lambda item: item[1], reverse=True):
        if count <= 0:
            continue
        if key.startswith("port_"):
            locode = key.split("port_", 1)[-1]
            info = port_info.get(locode)
            label = info["name"] if info and info["name"] else locode
        elif key.startswith("exit_"):
            zone = key.split("exit_", 1)[-1]
            label = f"Sortie {zone.capitalize()}"
        elif key in {"unknown", "unspecified"}:
            continue
        else:
            label = key
        labels.append(label)
        counts.append(count)

    if not counts:
        raise ValueError("Aucune donnée exploitable après filtrage.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))
    colors = colors_for_labels(labels)
    ax.pie(counts, labels=labels, autopct="%1.1f%%", startangle=90, colors=colors)
    ax.set_title("Répartition des destinations après entrée")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def render_gate_category_pies(zone_key, output_dir=Path("figures/gates")):
    output_dir.mkdir(parents=True, exist_ok=True)
    category_counts = gate_category_distribution(zone_key)
    size_counts = gate_size_distribution(zone_key)
    zone_name = "Bosphore" if zone_key == "nord" else "Dardanelles"

    def make_pie(data, title, filename):
        if not data:
            raise ValueError(f"Aucune donnée pour {title}")
        labels = [lbl for lbl in data.keys() if lbl not in {"unknown", "unspecified"}]
        missing = sum(count for lbl, count in data.items() if lbl in {"unknown", "unspecified"})
        counts = [data[label] for label in labels]
        fig, ax = plt.subplots(figsize=(5, 5))
        colors = colors_for_labels(labels)
        ax.pie(counts, labels=labels, autopct="%1.1f%%", startangle=90, colors=colors)
        ax.set_title(title)
        if missing:
            total = sum(counts) + missing
            missing_pct = 100 * missing / total if total else 0
            ax.text(0.5, -0.1, f"{missing_pct:.1f}% de données manquantes", ha="center", va="center", transform=ax.transAxes)
        fig.tight_layout()
        path = output_dir / filename
        fig.savefig(path, dpi=200)
        plt.close(fig)
        return path

    category_path = make_pie(
        category_counts,
        f"Répartition des catégories ({zone_name})",
        f"{zone_key}_categories.png",
    )
    size_path = make_pie(
        size_counts,
        f"Répartition des tailles ({zone_name})",
        f"{zone_key}_sizes.png",
    )
    return category_path, size_path

if __name__ == "__main__":
    route_map_path = render_route_heatmap()
    print(f"Route map generated: {route_map_path.resolve()}")
    top_ports_path = render_top_ports_bar_chart()
    print(f"Port volume chart generated: {top_ports_path.resolve()}")
    top_grand_path = render_top_grand_destinations()
    print(f"Grand ship destinations chart generated: {top_grand_path.resolve()}")
    category_pie_path = render_category_pie_chart()
    print(f"Category pie chart generated: {category_pie_path.resolve()}")
    north_entries = render_gate_entry_chart("nord")
    print(f"North gate chart generated: {north_entries.resolve()}")
    south_entries = render_gate_entry_chart("sud")
    print(f"South gate chart generated: {south_entries.resolve()}")
    north_exits = render_gate_exit_chart("nord")
    print(f"North gate exit chart generated: {north_exits.resolve()}")
    south_exits = render_gate_exit_chart("sud")
    print(f"South gate exit chart generated: {south_exits.resolve()}")
    try:
        destination_path = render_destination_breakdown_pie()
    except ValueError as e:
        destination_path = None
        print(f"Destination breakdown skipped: {e}")
    else:
        print(f"Destination breakdown chart generated: {destination_path.resolve()}")
    for gate in ("nord", "sud"):
        cat_path, size_path = render_gate_category_pies(gate)
        print(f"{gate} gate category pie: {cat_path.resolve()}")
        print(f"{gate} gate size pie: {size_path.resolve()}")
