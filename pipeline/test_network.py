#!/usr/bin/env python3
from pathlib import Path
import json, os, urllib.request
from datetime import datetime, timezone

OUT=Path('out'); OUT.mkdir(exist_ok=True)
DATA=Path('work/data'); DATA.mkdir(parents=True,exist_ok=True)

def dl(url,path):
    if path.exists() and path.stat().st_size>0: return
    req=urllib.request.Request(url,headers={'User-Agent':'NJ-Transit-Score-Research/1.0'})
    with urllib.request.urlopen(req,timeout=300) as r, open(path,'wb') as f:
        while True:
            b=r.read(1<<20)
            if not b: break
            f.write(b)

urls={
 'osm':'https://download.geofabrik.de/north-america/us/new-jersey-latest.osm.pbf',
 'blocks':'https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_34_tabblock20.zip',
 'lodes':'https://lehd.ces.census.gov/data/lodes/LODES8/nj/wac/nj_wac_S000_JT00_2023.csv.gz',
}
for k,u in urls.items():
    suffix='.osm.pbf' if k=='osm' else ('.zip' if k=='blocks' else '.csv.gz')
    dl(u,DATA/f'{k}{suffix}')

from pyrosm import OSM
osm=OSM(str(DATA/'osm.osm.pbf'))
nodes,edges=osm.get_network(network_type='walking',nodes=True)
summary={
 'retrieved_at':datetime.now(timezone.utc).isoformat(),
 'file_sizes':{p.name:p.stat().st_size for p in DATA.iterdir()},
 'network_nodes':int(len(nodes)), 'network_edges':int(len(edges)),
 'node_columns':list(nodes.columns), 'edge_columns':list(edges.columns),
 'edge_length_nulls':int(edges['length'].isna().sum()) if 'length' in edges else None,
 'edge_length_min':float(edges['length'].min()) if 'length' in edges else None,
 'edge_length_max':float(edges['length'].max()) if 'length' in edges else None,
}
(OUT/'network_test.json').write_text(json.dumps(summary,indent=2))
nodes.head(1000).to_parquet(OUT/'network_nodes_sample.parquet')
edges.head(1000).to_parquet(OUT/'network_edges_sample.parquet')
print(json.dumps(summary,indent=2))
