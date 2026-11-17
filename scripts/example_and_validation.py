"""Reproduces the worked example and the validation numbers quoted in the README.

Run from the repository root (needs data/data_sensors.parquet from Zenodo, see the README):

    uv run python scripts/example_and_validation.py            # IJmond, 1-15 March 2025
    uv run python scripts/example_and_validation.py 2025-03-01 2025-03-15

It runs the analysis functions of the notebook app (notebooks/04_hotspot_screening_app.ipynb, the text of its
launcher cell) with the notebook's default settings, so the numbers are exactly what the app produces for that window.
Then it
  1. counts what was flagged in IJmond,
  2. picks the worked example and draws it (docs/example/ijmond_example.png),
  3. compares the sensors with the official Luchtmeetnet stations (validation).
Nothing here changes the method; it only reads the results.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import types
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "04_hotspot_screening_app.ipynb"
FIGURE = ROOT / "docs" / "example" / "ijmond_example.png"
IJMOND = dict(lat=(52.435, 52.56), lon=(4.53, 4.72))  # the box used throughout the README
MAX_PEAK_PM = 100.0  # the example must not be an obviously faulty sensor (readings far above 100 ug/m3)


def load_app() -> types.ModuleType:
    """The analysis code of the notebook: the text of APP_SOURCE in its first cell, loaded as a module."""
    cell = "".join(json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"][0]["source"])
    start = cell.index("APP_SOURCE = r'''") + len("APP_SOURCE = r'''")
    source = cell[start:cell.index("'''\n", start)]
    mod = types.ModuleType("hotspot_app")
    mod.__file__ = str(ROOT / "output" / "pm25_hotspot_app.py")  # where the notebook writes the app
    sys.modules["hotspot_app"] = mod  # dataclasses look the module up here
    exec(compile(source, "hotspot_app", "exec"), mod.__dict__)  # definitions only; the app itself is not started
    return mod


def in_ijmond(d: pd.DataFrame) -> pd.Series:
    return d.lat.between(*IJMOND["lat"]) & d.lon.between(*IJMOND["lon"])


def dist_m(lat1, lon1, lat2, lon2):
    return np.hypot((lat2 - lat1) * 111_320.0, (lon2 - lon1) * 111_320.0 * np.cos(np.radians((lat1 + lat2) / 2)))


def official_stations(start, end):
    """Hourly PM2.5 of the Luchtmeetnet stations in IJmond (UTC hour starts) and the station table."""
    meta = pd.read_csv(ROOT / "data" / "reference_station_metadata.csv")
    meta = meta[meta.breedtegraad.between(*IJMOND["lat"]) & meta.lengtegraad.between(*IJMOND["lon"])]
    ref = pq.read_table(ROOT / "data" / "reference_measurements.parquet",
                        filters=[("component", "=", "PM2.5"), ("meetlocatie_id", "in", meta.meetlocatie_id.tolist())]
                        ).to_pandas()
    ref["hour"] = pd.to_datetime(ref.begindatumtijd, utc=True)  # "...T00:00:00+01:00" -> UTC
    ref = ref[(ref.hour >= start) & (ref.hour < end)]
    return ref.pivot_table(index="hour", columns="meetlocatie_id", values="waarde"), meta.set_index("meetlocatie_id")


def main() -> None:
    start = sys.argv[1] if len(sys.argv) > 2 else "2025-03-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2025-03-15"
    app = load_app()
    log = io.StringIO()
    with contextlib.redirect_stdout(log):  # the app prints a lot of progress
        a = app.run_pipeline(app.Config(start=start, end=end, save_outputs=False))
    r, summary, events = a["features"], a["summary"], a["events"]
    r["hotspot"] = r.hotspot.astype(bool)
    r["eligible"] = r.eligible.astype(bool)
    ij = summary[in_ijmond(summary)]
    rij = r[r.sensor.isin(ij.index)]

    print(f"WINDOW {a['start']:%Y-%m-%d %H:%M} to {a['end']:%Y-%m-%d %H:%M} UTC (end exclusive), notebook default settings")
    print(f"all sensors in the run: {len(summary)}; in IJmond: {len(ij)}")
    print(f"IJmond sensor-hours: observed {len(rij):,}, assessable {int(rij.eligible.sum()):,}, flagged {int(rij.hotspot.sum()):,}"
          f" ({100 * rij.hotspot.mean():.1f} %)")
    print("IJmond persistence classes:", ij.persistence_class.value_counts().to_dict())
    status = rij.wind_status.value_counts()
    print("IJmond wind status of sensor-hours:", {k: f"{v:,} ({100 * v / len(rij):.0f} %)" for k, v in status.items()})
    print("wind stations used by IJmond sensors:",
          rij.groupby("weather_station").sensor.nunique().rename("sensors").to_dict())
    ev = events.merge(summary[["lat", "lon"]], left_on="sensor", right_index=True)
    ev = ev[in_ijmond(ev)]
    print(f"IJmond episodes: {len(ev)} ({int((ev.event_class == 'sustained').sum())} sustained)")

    # --- the worked example: longest sustained episode with a wind direction and an upwind comparison in every hour
    peak_pm = rij.groupby("event_id").pm.max()
    cand = ev[(ev.event_class == "sustained") & (ev.wind_comparable_hours == ev.hours)
              & (ev.wind_supported_hours == ev.hours) & (ev.event_id.map(peak_pm) < MAX_PEAK_PM)]
    ex = cand.sort_values(["hours", "peak_excess"], ascending=False).iloc[0]
    sid = ex.sensor
    x = r[r.sensor == sid].sort_values("hour").set_index("hour")
    e = x[x.event_id == ex.event_id]
    print(f"\nEXAMPLE {sid} at {summary.loc[sid, 'lat']:.4f}, {summary.loc[sid, 'lon']:.4f}; "
          f"episode {ex.start:%d %b %H:%M} to {ex.end_exclusive:%d %b %H:%M} UTC ({int(ex.hours)} h, {ex.event_class})")
    print(f"  wind station {x.weather_station.iloc[0]} at {x.weather_distance_km.iloc[0]:.1f} km; "
          f"neighbours reporting (median) {int(x.neighbor_count.median())}; "
          f"flagged hours of this sensor in the window: {int(x.hotspot.sum())} of {len(x)}")
    print(f"  PM2.5 {e.pm.min():.1f}-{e.pm.max():.1f}; local excess {e.local_excess.min():.1f}-{e.local_excess.max():.1f} "
          f"(mean {ex.mean_excess:.1f}); robust score {e.robust_z.min():.2f}-{e.robust_z.max():.2f}")
    print(f"  wind from {sorted(set(e.wind_sector))} (dd {e.dd.min():.0f}-{e.dd.max():.0f} deg); "
          f"upwind excess {e.upwind_excess.min():.1f}-{e.upwind_excess.max():.1f} with {int(e.upwind_neighbor_count.min())}-"
          f"{int(e.upwind_neighbor_count.max())} upwind neighbours; wind-supported {int(ex.wind_supported_hours)} of {int(ex.hours)} h")
    f = x[x.hotspot]
    shares = pd.DataFrame({"flagged": f.wind_sector.value_counts(), "assessable": x[x.eligible].wind_sector.value_counts()}).fillna(0)
    print("  this sensor's flagged hours by wind sector:", {k: int(v) for k, v in shares.flagged.items() if v})

    # independent check against the nearest official station, same hours
    piv, st = official_stations(a["start"], a["end"])
    d = {sid_: dist_m(summary.loc[sid, "lat"], summary.loc[sid, "lon"], row.breedtegraad, row.lengtegraad)
         for sid_, row in st.iterrows()}
    near = min(d, key=d.get)
    names = st.meetlocatie_naam.to_dict()
    hrs = e.index[e.hotspot]
    sub = piv.loc[piv.index.intersection(hrs)]
    at_or_below = int((sub[near] <= sub.median(axis=1)).sum())
    print(f"  nearest official station: {names[near].strip()} ({st.loc[near, 'stationstype']}) at {d[near]:.0f} m; during the "
          f"{len(sub)} flagged hours it read {sub[near].min():.1f}-{sub[near].max():.1f}; the six stations read "
          f"{sub.min().min():.1f}-{sub.max().max():.1f}; at or below the median of the six stations in {at_or_below} of {len(sub)} hours")
    print("  station types in IJmond:", st.stationstype.value_counts().to_dict())

    # --- figure: map of the hour with the highest score in the episode + the sensor's time series
    hour = e.robust_z.idxmax()
    cur = r[r.hour == hour].merge(summary[["lat", "lon"]], left_on="sensor", right_index=True)
    cur = cur[cur.lat.between(IJMOND["lat"][0] - 0.05, IJMOND["lat"][1] + 0.05)
              & cur.lon.between(IJMOND["lon"][0] - 0.08, IJMOND["lon"][1] + 0.08)]
    centre = ((IJMOND["lat"][0] + IJMOND["lat"][1]) / 2, (IJMOND["lon"][0] + IJMOND["lon"][1]) / 2)
    ids = set(summary.index[np.hypot(*app.region_xy(summary.lat, summary.lon, *centre)) <= 8 + 3])
    lower, upper = app.color_limits(r[r.sensor.isin(ids)].merge(summary[["lat", "lon"]], left_on="sensor", right_index=True), "local_excess")
    app.SURFACE_CMAP_ORIG = app.SURFACE_CMAP
    surf = app.make_surface(cur, centre[0], centre[1], 8.0, 3.0, "local_excess", lower, upper)
    fig, (axm, axt) = plt.subplots(1, 2, figsize=(15, 6), gridspec_kw={"width_ratios": [1, 1.35]})
    if surf is not None:
        img, ((south, west), (north, east)) = surf
        axm.imshow(img, extent=[west, east, south, north], origin="upper", aspect="auto", zorder=1)
    axm.set_xlim(IJMOND["lon"][0] - 0.02, IJMOND["lon"][1] + 0.02)
    axm.set_ylim(IJMOND["lat"][0] - 0.01, IJMOND["lat"][1] + 0.01)
    axm.set_aspect(1 / np.cos(np.radians(centre[0])))
    flag, other = cur[cur.hotspot], cur[~cur.hotspot]
    axm.scatter(other.lon, other.lat, s=26, c="white", edgecolors="#193747", linewidths=1.2, zorder=3, label="reporting, not flagged")
    axm.scatter(flag.lon, flag.lat, s=70, c="#ee4b32", edgecolors="#971b1b", linewidths=1.5, zorder=4, label="candidate hotspot")
    axm.scatter([summary.loc[sid, "lon"]], [summary.loc[sid, "lat"]], s=330, facecolors="none", edgecolors="black",
                linewidths=2, zorder=5, label=f"example sensor {sid[-3:]}")
    axm.scatter(st.lengtegraad, st.breedtegraad, marker="s", s=60, c="black", zorder=5, label="official station")
    for _, row in st.iterrows():
        axm.annotate(row.meetlocatie_naam.strip().split("-")[0][:14], (row.lengtegraad, row.breedtegraad), fontsize=7,
                     xytext=(4, 4), textcoords="offset points", zorder=6)
    wd = float(cur.set_index("sensor").loc[sid, "dd"])
    axm.annotate("", xy=(0.12 - 0.07 * np.sin(np.radians(wd)), 0.88 - 0.07 * np.cos(np.radians(wd))), xytext=(0.12, 0.88),
                 xycoords="axes fraction", arrowprops=dict(arrowstyle="-|>", lw=2.5, color="#1f4e79"), zorder=7)
    axm.text(0.03, 0.97, f"wind from {cur.set_index('sensor').loc[sid, 'wind_sector']} ({wd:.0f}°)", transform=axm.transAxes,
             va="top", fontsize=9, color="#1f4e79", weight="bold", zorder=7)
    axm.legend(loc="lower right", fontsize=7.5, framealpha=0.9)
    axm.set_xlabel("longitude"); axm.set_ylabel("latitude")
    axm.set_title(f"IJmond, {hour:%d %b %Y %H:%M}-{hour + pd.Timedelta(hours=1):%H:%M} UTC\n"
                  f"surface: sensor PM2.5 minus median of neighbours (µg/m³, {lower:.1f} to {upper:.1f}); not measured between sensors",
                  fontsize=9)
    lo, hi = ex.start - pd.Timedelta(hours=30), ex.end_exclusive + pd.Timedelta(hours=30)
    w = x.loc[lo:hi]
    full = w.reindex(pd.date_range(w.index.min(), w.index.max(), freq="h"))
    axt.axvspan(ex.start, ex.end_exclusive, color="#ee4b32", alpha=0.12, label="sustained episode")
    axt.plot(full.index, full.pm, color="#1f77b4", label=f"sensor {sid[-3:]} (raw PM2.5)")
    axt.plot(full.index, full.local_background, color="#ff7f0e", alpha=0.85, label="median of its neighbours")
    axt.plot(piv.index, piv[near], color="black", ls="--", lw=1.4, label=f"official {names[near].strip()} ({d[near]:.0f} m)")
    axt.scatter(e.index, e.pm, color="#ee4b32", s=28, zorder=5, label="flagged hours")
    axt.set_xlim(lo, hi)
    axt.set_ylabel("PM2.5 (µg/m³; sensors in reported units)"); axt.set_xlabel("time (UTC)")
    axt.grid(alpha=0.25); axt.legend(fontsize=8, loc="upper right")
    axt.set_title(f"Sensor {sid[-3:]}: local excess {e.local_excess.min():.1f}-{e.local_excess.max():.1f} µg/m³, "
                  f"score up to {e.robust_z.max():.1f}, wind from the north in all {int(ex.hours)} hours", fontsize=9)
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=130)
    plt.close(fig)
    print(f"  figure: {FIGURE.relative_to(ROOT)} (map hour {hour:%Y-%m-%d %H:%M} UTC)")

    # --- validation against the official stations
    exc = piv[piv.notna().sum(axis=1) >= 4]
    exc = exc.sub(exc.median(axis=1), axis=0)  # station minus the median of the stations = the official "local excess"
    rows = []
    for sid_, row in st.iterrows():
        for sensor, sv in ij.iterrows():
            dm = dist_m(row.breedtegraad, row.lengtegraad, sv.lat, sv.lon)
            if dm > 1000:
                continue
            xs = r[r.sensor == sensor].set_index("hour")
            j = pd.DataFrame({"s": xs.local_excess, "flag": xs.hotspot, "o": exc[sid_]}).dropna(subset=["s", "o"])
            if len(j) < 100:
                continue
            j["flag"] = j["flag"].astype(bool)  # aligning the two hour indexes had turned it into object dtype
            rows.append(dict(sensor=sensor, station=sid_, m=dm, hours=len(j), spearman=j.s.corr(j.o, method="spearman"),
                             flagged=int(j.flag.sum()), o_flag=j.loc[j.flag, "o"].mean() if j.flag.any() else np.nan,
                             o_rest=j.loc[~j.flag, "o"].mean()))
    v = pd.DataFrame(rows)
    f3 = v[v.flagged >= 3]
    print(f"\nVALIDATION against the {len(st)} official IJmond stations (hours with at least 4 stations reporting)")
    print(f"  sensor-station pairs within 1 km: {len(v)} ({v.sensor.nunique()} sensors, {v.station.nunique()} stations)")
    print(f"  Spearman correlation of sensor local excess with station excess: median {v.spearman.median():.2f}, "
          f"range {v.spearman.min():.2f} to {v.spearman.max():.2f}; positive in {int((v.spearman > 0).sum())} of {len(v)} pairs")
    print(f"  official-station excess in the sensor's flagged hours: mean {f3.o_flag.mean():+.1f} ug/m3 versus "
          f"{f3.o_rest.mean():+.1f} in its other hours (pairs with at least 3 flagged hours: {len(f3)})")


if __name__ == "__main__":
    main()
