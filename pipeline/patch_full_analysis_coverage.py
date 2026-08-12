#!/usr/bin/env python3
from pathlib import Path

p = Path('pipeline/full_analysis/prepare_inputs.py')
s = p.read_text()

# Use the current Mobility Database mirror when the producer endpoint returns an empty archive.
s = s.replace(
    '"url": "https://boxcar-gtfs.vercel.app/api/gtfs",',
    '"url": "https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-boxcar-gtfs-3105.zip?alt=media",'
)

# Pandas may expose read-only NumPy views under copy-on-write. Parent-station
# coordinate substitution requires mutable arrays.
s = s.replace(
    'access_lat = stops["stop_lat_num"].to_numpy(float)\n                access_lon = stops["stop_lon_num"].to_numpy(float)',
    'access_lat = stops["stop_lat_num"].to_numpy(float).copy()\n                access_lon = stops["stop_lon_num"].to_numpy(float).copy()'
)

# Retain valid ranks when a small number of landless tracts have undefined scores.
s = s.replace(
    'score["ts_pct_current"] = rankdata(score["ts_current"], method="average") / len(score) * 100.0',
    'score["ts_pct_current"] = score["ts_current"].rank(method="average", pct=True) * 100.0'
)

p.write_text(s)
print('Applied feed-coverage, mutable-coordinate, and valid-score-rank corrections.')
