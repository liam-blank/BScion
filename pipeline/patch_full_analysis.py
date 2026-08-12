#!/usr/bin/env python3
from pathlib import Path

root = Path('pipeline/full_analysis')
prep = root / 'prepare_inputs.py'
metrics = root / 'metrics.cpp'

s = prep.read_text()

# Census tract requests require both the state and county geography clauses.
s = s.replace(
    '"acs": "https://api.census.gov/data/2024/acs/acs5?get=NAME,B01003_001E,B11001_001E&for=tract:*&in=state:34",',
    '"acs": "https://api.census.gov/data/2024/acs/acs5?get=NAME%2CB01003_001E%2CB11001_001E&for=tract%3A%2A&in=state%3A34&in=county%3A%2A",'
)
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

print('Applied Census, pedestrian-network, connector, and frequent-service corrections.')
