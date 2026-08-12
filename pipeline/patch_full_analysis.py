#!/usr/bin/env python3
from pathlib import Path

root = Path('pipeline/full_analysis')
prep = root / 'prepare_inputs.py'
metrics = root / 'metrics.cpp'

s = prep.read_text()

# Census now requires an API key for ACS queries. Use the authoritative,
# table-based 2024 ACS 5-year summary files, which remain publicly downloadable.
s = s.replace(
    '"acs": "https://api.census.gov/data/2024/acs/acs5?get=NAME,B01003_001E,B11001_001E&for=tract:*&in=state:34",',
    '"acs_population": "https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b01003.dat",\n    "acs_households": "https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b11001.dat",'
)

old_acs = '''    # ACS tract controls.
    acs_path = DATA / "acs_2024_tracts.json"
    if not acs_path.exists():
        rec = download(SOURCE_URLS["acs"], acs_path)
        rec["dataset"] = "acs_2024_tracts"
        source_records.append(rec)
    acs_raw = json.loads(acs_path.read_text())
    acs = pd.DataFrame(acs_raw[1:], columns=acs_raw[0])
    acs["GEOID"] = acs["state"].astype(str) + acs["county"].astype(str) + acs["tract"].astype(str)
    acs["pop_2024"] = pd.to_numeric(acs["B01003_001E"], errors="coerce").fillna(0)
    acs["households_2024"] = pd.to_numeric(acs["B11001_001E"], errors="coerce").fillna(0)
    acs = acs[["GEOID", "NAME", "pop_2024", "households_2024"]]
'''
new_acs = '''    # ACS tract controls from the keyless, table-based 2024 ACS 5-year Summary File.
    acs_pop_path = DATA / "acsdt5y2024-b01003.dat"
    acs_hh_path = DATA / "acsdt5y2024-b11001.dat"
    for dataset, key, path in (("acs_2024_population", "acs_population", acs_pop_path), ("acs_2024_households", "acs_households", acs_hh_path)):
        rec = download(SOURCE_URLS[key], path)
        rec["dataset"] = dataset
        source_records.append(rec)
    pop_sf = pd.read_csv(acs_pop_path, sep="|", dtype={"GEO_ID": str}, usecols=["GEO_ID", "B01003_E001"])
    hh_sf = pd.read_csv(acs_hh_path, sep="|", dtype={"GEO_ID": str}, usecols=["GEO_ID", "B11001_E001"])
    pop_sf = pop_sf[pop_sf["GEO_ID"].str.startswith("1400000US34", na=False)].copy()
    hh_sf = hh_sf[hh_sf["GEO_ID"].str.startswith("1400000US34", na=False)].copy()
    pop_sf["GEOID"] = pop_sf["GEO_ID"].str[-11:]
    hh_sf["GEOID"] = hh_sf["GEO_ID"].str[-11:]
    acs = pop_sf[["GEOID", "B01003_E001"]].merge(hh_sf[["GEOID", "B11001_E001"]], on="GEOID", how="outer")
    acs["pop_2024"] = pd.to_numeric(acs["B01003_E001"], errors="coerce").fillna(0)
    acs["households_2024"] = pd.to_numeric(acs["B11001_E001"], errors="coerce").fillna(0)
    county_names = {"001":"Atlantic","003":"Bergen","005":"Burlington","007":"Camden","009":"Cape May","011":"Cumberland","013":"Essex","015":"Gloucester","017":"Hudson","019":"Hunterdon","021":"Mercer","023":"Middlesex","025":"Monmouth","027":"Morris","029":"Ocean","031":"Passaic","033":"Salem","035":"Somerset","037":"Sussex","039":"Union","041":"Warren"}
    acs["NAME"] = "Census Tract " + acs["GEOID"].str[-6:] + ", " + acs["GEOID"].str[2:5].map(county_names).fillna("Unknown") + " County, New Jersey"
    acs = acs[["GEOID", "NAME", "pop_2024", "households_2024"]]
'''
if old_acs not in s:
    raise RuntimeError('ACS-control patch target missing')
s = s.replace(old_acs, new_acs)

s = s.replace('MAX_STOP_SNAP_M = 300.0\n', 'MAX_STOP_SNAP_M = 300.0\nMAX_BUS_STOP_SNAP_M = 100.0\n')

old = '''    origins = blocks[(blocks["scaled_pop_2024"] > 0) | (blocks["jobs_2023"] > 0)].copy()
    origins = origins[["block_geoid", "tract_geoid", "scaled_pop_2024", "pop_2020", "housing_2020", "jobs_2023", "origin_lon", "origin_lat"]]
    origins = origins[np.isfinite(origins["origin_lon"]) & np.isfinite(origins["origin_lat"])].copy()
    origins["origin_idx"] = np.arange(len(origins), dtype=np.int32)
'''
new = '''    origins = blocks[(blocks["scaled_pop_2024"] > 0) | (blocks["jobs_2023"] > 0)].copy()
    origins = origins[np.isfinite(origins["origin_lon"]) & np.isfinite(origins["origin_lat"])].copy()
    origin_polygons_26918 = origins.geometry.to_crs(26918).reset_index(drop=True)
    origins = origins[["block_geoid", "tract_geoid", "scaled_pop_2024", "pop_2020", "housing_2020", "jobs_2023", "origin_lon", "origin_lat"]].reset_index(drop=True)
    origins["origin_idx"] = np.arange(len(origins), dtype=np.int32)
'''
if old not in s:
    raise RuntimeError('origin-selection patch target missing')
s = s.replace(old, new)

old = '''    ox, oy = to_nj.transform(origins["origin_lon"].to_numpy(float), origins["origin_lat"].to_numpy(float))
    odist, onode = tree.query(np.column_stack([ox, oy]), k=1, workers=-1)
    origins["node_idx"] = onode.astype(np.int32)
    origins["snap_distance_m"] = odist
    origins["network_connected"] = odist <= MAX_ORIGIN_SNAP_M

    sx, sy = to_nj.transform(stops_used["access_lon"].to_numpy(float), stops_used["access_lat"].to_numpy(float))
    sdist, snode = tree.query(np.column_stack([sx, sy]), k=1, workers=-1)
    stops_used["node_idx"] = snode.astype(np.int32)
    stops_used["snap_distance_m"] = sdist
    stops_used["network_connected"] = sdist <= MAX_STOP_SNAP_M
'''
new = '''    ox, oy = to_nj.transform(origins["origin_lon"].to_numpy(float), origins["origin_lat"].to_numpy(float))
    od_all, on_all = tree.query(np.column_stack([ox, oy]), k=12, workers=-1)
    od_all = np.atleast_2d(od_all) if len(origins) == 1 else od_all
    on_all = np.atleast_2d(on_all) if len(origins) == 1 else on_all
    chosen_nodes = np.full(len(origins), -1, dtype=np.int32)
    chosen_dist = np.full(len(origins), np.nan, dtype=float)
    snap_method = np.full(len(origins), "disconnected", dtype=object)
    for i, poly in enumerate(origin_polygons_26918):
        for dist, node in zip(np.atleast_1d(od_all[i]), np.atleast_1d(on_all[i])):
            if float(dist) > MAX_ORIGIN_SNAP_M:
                break
            if poly.buffer(0.25).covers(Point(float(node_xy[int(node), 0]), float(node_xy[int(node), 1]))):
                chosen_nodes[i] = int(node); chosen_dist[i] = float(dist); snap_method[i] = "within_block"; break
        if chosen_nodes[i] < 0 and float(np.atleast_1d(od_all[i])[0]) <= 75.0:
            chosen_nodes[i] = int(np.atleast_1d(on_all[i])[0]); chosen_dist[i] = float(np.atleast_1d(od_all[i])[0]); snap_method[i] = "short_external_connector"
    origins["node_idx"] = chosen_nodes
    origins["snap_distance_m"] = chosen_dist
    origins["snap_method"] = snap_method
    origins["network_connected"] = origins["node_idx"] >= 0

    sx, sy = to_nj.transform(stops_used["access_lon"].to_numpy(float), stops_used["access_lat"].to_numpy(float))
    sdist, snode = tree.query(np.column_stack([sx, sy]), k=1, workers=-1)
    stops_used["node_idx"] = snode.astype(np.int32)
    stops_used["snap_distance_m"] = sdist
    stop_mode = np.full(len(stops_used), 3, dtype=np.int8)
    if len(events):
        event_modes = trip_array["mode"][events["trip"]]
        for stop_idx, mode in zip(events["stop"], event_modes):
            if mode in (1, 2): stop_mode[int(stop_idx)] = int(mode)
            elif stop_mode[int(stop_idx)] == 3: stop_mode[int(stop_idx)] = int(mode)
    stops_used["analysis_mode_code"] = stop_mode
    stops_used["snap_limit_m"] = np.where(stops_used["analysis_mode_code"].eq(0), MAX_BUS_STOP_SNAP_M, MAX_STOP_SNAP_M)
    stops_used["network_connected"] = stops_used["snap_distance_m"] <= stops_used["snap_limit_m"]
'''
if old not in s:
    raise RuntimeError('network-snap patch target missing')
s = s.replace(old, new)

# OSM.get_network returns physical segments. Walking graph arcs must be reciprocal.
old = '''    edge_array = np.empty(int(finite.sum()), dtype=edge_dtype)
    edge_array["u"] = uidx[finite]
    edge_array["v"] = vidx[finite]
    edge_array["w"] = length[finite]
    edge_array.tofile(INT / "edges.bin")
'''
new = '''    forward = np.empty(int(finite.sum()), dtype=edge_dtype)
    forward["u"] = uidx[finite]
    forward["v"] = vidx[finite]
    forward["w"] = length[finite]
    reverse = np.empty(len(forward), dtype=edge_dtype)
    reverse["u"] = forward["v"]
    reverse["v"] = forward["u"]
    reverse["w"] = forward["w"]
    edge_array = np.concatenate([forward, reverse])
    edge_array.tofile(INT / "edges.bin")
'''
if old not in s:
    raise RuntimeError('pedestrian-edge patch target missing')
s = s.replace(old, new)

s = s.replace(
    '"disconnected_origin_blocks": int((~origins["network_connected"]).sum()),',
    '"disconnected_origin_blocks": int((~origins["network_connected"]).sum()),\n        "within_block_origin_connectors": int((origins["snap_method"] == "within_block").sum()),\n        "short_external_origin_connectors": int((origins["snap_method"] == "short_external_connector").sum()),'
)
s = s.replace(
    '"max_stop_snap_m": MAX_STOP_SNAP_M,',
    '"max_bus_stop_snap_m": MAX_BUS_STOP_SNAP_M,\n            "max_rail_stop_snap_m": MAX_STOP_SNAP_M,'
)
prep.write_text(s)

m = metrics.read_text()
old = '''    for(const auto&kv:bus_counts)if(kv.second>=4){m.frequent_bus=1;break;}
    for(int h=0;h<18;h++){m.useful15+=h15[h];m.useful30+=h30[h];m.useful60+=h60[h];}
'''
new = '''    bool bus_h15[18]={};
    for(const auto&kv:bus_counts)if(kv.second>=4){int hour=(int)(kv.first&0xff);if(hour>=0&&hour<18)bus_h15[hour]=true;}
    int bus_useful15=0;
    for(int h=0;h<18;h++){m.useful15+=h15[h];m.useful30+=h30[h];m.useful60+=h60[h];bus_useful15+=bus_h15[h];}
    m.frequent_bus=bus_useful15>=6;
'''
if old not in m:
    raise RuntimeError('frequent-bus patch target missing')
metrics.write_text(m.replace(old, new))

print('Applied ACS summary-file, pedestrian-network, connector, and frequent-service corrections.')
