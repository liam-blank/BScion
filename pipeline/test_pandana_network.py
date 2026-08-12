#!/usr/bin/env python3
from pathlib import Path
import json, time, urllib.request
from datetime import datetime, timezone
OUT=Path('out_pandana_test'); OUT.mkdir(exist_ok=True)
DATA=Path('work/pandana'); DATA.mkdir(parents=True,exist_ok=True)
pbf=DATA/'new-jersey-latest.osm.pbf'
if not pbf.exists():
    req=urllib.request.Request('https://download.geofabrik.de/north-america/us/new-jersey-latest.osm.pbf',headers={'User-Agent':'NJ-Transit-Score-Service-Access/1.0'})
    with urllib.request.urlopen(req,timeout=600) as r, open(pbf,'wb') as f:
        while True:
            b=r.read(1<<20)
            if not b: break
            f.write(b)
import pandas as pd, numpy as np
from pyrosm import OSM
from pyproj import Transformer
import pandana as pdna
marks={}; t=time.time()
osm=OSM(str(pbf)); nodes,edges=osm.get_network(network_type='walking',nodes=True); marks['extract_s']=time.time()-t
# Drop self loops and invalid edge lengths.
edges=edges.loc[edges['u'].notna() & edges['v'].notna() & edges['length'].notna() & (edges['length']>0),['u','v','length']].copy()
node_ids=pd.Index(nodes['id'].astype('int64'))
t=time.time(); u=node_ids.get_indexer(edges['u'].astype('int64')); v=node_ids.get_indexer(edges['v'].astype('int64')); ok=(u>=0)&(v>=0); u=u[ok].astype('int32'); v=v[ok].astype('int32'); w=edges.loc[ok,'length'].astype('float32').reset_index(drop=True); marks['index_s']=time.time()-t
tr=Transformer.from_crs(4326,32111,always_xy=True); t=time.time(); x,y=tr.transform(nodes['lon'].to_numpy(),nodes['lat'].to_numpy()); marks['project_s']=time.time()-t
x=pd.Series(np.asarray(x,dtype='float64')); y=pd.Series(np.asarray(y,dtype='float64')); weights=pd.DataFrame({'distance':w})
t=time.time(); net=pdna.Network(x,y,pd.Series(u),pd.Series(v),weights,twoway=True); marks['network_s']=time.time()-t
# Query 20 nodes distributed across the network.
sources=np.linspace(0,len(nodes)-1,20,dtype='int32'); t=time.time(); result=net.nodes_in_range(sources,1200); marks['query_s']=time.time()-t
summary={'retrieved_at':datetime.now(timezone.utc).isoformat(),'pbf_bytes':pbf.stat().st_size,'nodes':len(nodes),'edges':len(w),'result_rows':len(result),'result_columns':list(result.columns),'marks':marks,'sample':result.head(20).to_dict('records')}
(OUT/'pandana_test.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='sample'},indent=2))
