#!/usr/bin/env python3
from __future__ import annotations
import csv, gzip, hashlib, io, json, math, os, pathlib, shutil, subprocess, urllib.parse, urllib.request, zipfile
from collections import defaultdict
from datetime import date, datetime, timezone

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer
from pyrosm import OSM
from scipy.spatial import cKDTree
from shapely.geometry import Point

from feed_config import FEEDS

ROOT=pathlib.Path('work/full'); DATA=ROOT/'data'; FEEDDIR=ROOT/'feeds'; PREP=ROOT/'prepared'; OUT=pathlib.Path('out')
for p in (DATA,FEEDDIR,PREP,OUT): p.mkdir(parents=True,exist_ok=True)
UA='NJ-Transit-Score-Accessible-Service/1.0 (public-interest research)'
WEEKDAY=date(2026,8,18); SATURDAY=date(2026,8,22)
NJ_BBOX=(-75.65,38.82,-73.85,41.50)

URLS={
 'osm':'https://download.geofabrik.de/north-america/us/new-jersey-latest.osm.pbf',
 'blocks':'https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_34_tabblock20.zip',
 'lodes':'https://lehd.ces.census.gov/data/lodes/LODES8/nj/wac/nj_wac_S000_JT00_2023.csv.gz',
}

def download(url:pathlib.Path|str,path:pathlib.Path,timeout=600):
 if path.exists() and path.stat().st_size>0: return
 req=urllib.request.Request(str(url),headers={'User-Agent':UA})
 with urllib.request.urlopen(req,timeout=timeout) as r, open(path,'wb') as f:
  while True:
   b=r.read(1<<20)
   if not b: break
   f.write(b)

def sha256(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def zcsv(z,name):
 with z.open(name) as f:
  return pd.read_csv(f,encoding='utf-8-sig',low_memory=False,dtype=str)

def sec(t):
 try:
  h,m,s=map(int,str(t).split(':')); return h*3600+m*60+s
 except Exception: return np.nan

def active_services(z,d):
 ds=d.strftime('%Y%m%d'); wd=d.strftime('%A').lower(); active=set()
 if 'calendar.txt' in z.namelist():
  cal=zcsv(z,'calendar.txt').fillna('')
  for r in cal.to_dict('records'):
   if str(r.get('start_date',''))<=ds<=str(r.get('end_date','')) and str(r.get(wd,''))=='1': active.add(str(r.get('service_id','')))
 if 'calendar_dates.txt' in z.namelist():
  cd=zcsv(z,'calendar_dates.txt').fillna('')
  for r in cd.to_dict('records'):
   if str(r.get('date',''))==ds:
    sid=str(r.get('service_id',''))
    if str(r.get('exception_type',''))=='1': active.add(sid)
    elif str(r.get('exception_type',''))=='2': active.discard(sid)
 return active

def date_span(z):
 starts=[]; ends=[]
 if 'calendar.txt' in z.namelist():
  d=zcsv(z,'calendar.txt').fillna(''); starts+=d.get('start_date',pd.Series(dtype=str)).tolist(); ends+=d.get('end_date',pd.Series(dtype=str)).tolist()
 if 'calendar_dates.txt' in z.namelist():
  d=zcsv(z,'calendar_dates.txt').fillna(''); vals=d.get('date',pd.Series(dtype=str)).tolist(); starts+=vals; ends+=vals
 starts=[str(x) for x in starts if str(x) not in ('','nan')]; ends=[str(x) for x in ends if str(x) not in ('','nan')]
 return (min(starts) if starts else '',max(ends) if ends else '')

def mode_group(feed_id,route_type,route_short=''):
 try: rt=int(float(route_type))
 except: rt=3
 if feed_id=='amtrak': return 'bus' if rt in (3,700,701,702,703,704,705,706,707,708,709,710,711,712,713,714,715,716) else 'rail'
 if rt==4 or 1000<=rt<1100: return 'ferry'
 if rt in (0,1,2,5,6,7,12) or 100<=rt<700 or 900<=rt<1000: return 'rail'
 return 'bus'

def feed_archives(path,feed_id):
 outer=zipfile.ZipFile(path)
 names=set(outer.namelist()); req={'stops.txt','routes.txt','trips.txt','stop_times.txt'}
 if req.issubset(names): return [(feed_id,outer)]
 result=[]
 for n in sorted(names):
  if n.lower().endswith('.zip'):
   try:
    inner=zipfile.ZipFile(io.BytesIO(outer.read(n)))
    if req.issubset(set(inner.namelist())):
     suffix='rail' if 'rail' in n.lower() else ('bus' if 'bus' in n.lower() else pathlib.Path(n).stem.lower())
     result.append((feed_id+'_'+suffix,inner))
   except Exception: pass
 return result

def frequency_expansion(z,trips,st,active,feedseg,daylabel):
 # Returns scheduled calls for active trips. Frequency-based trips are expanded from their template offsets.
 t=trips[trips.service_id.astype(str).isin(active)].copy()
 if t.empty: return pd.DataFrame(),0
 st=st[st.trip_id.astype(str).isin(t.trip_id.astype(str))].copy()
 st['dep_seconds']=st['departure_time'].map(sec)
 st=st[np.isfinite(st.dep_seconds)]
 freq_rows=0
 if 'frequencies.txt' not in z.namelist():
  return st,0
 fr=zcsv(z,'frequencies.txt').fillna('')
 fr=fr[fr.trip_id.astype(str).isin(t.trip_id.astype(str))]
 if fr.empty: return st,0
 freq_rows=len(fr); normal=st[~st.trip_id.astype(str).isin(fr.trip_id.astype(str))].copy(); expanded=[normal]
 grouped={k:v.sort_values('stop_sequence') for k,v in st.groupby(st.trip_id.astype(str))}
 for r in fr.to_dict('records'):
  tid=str(r['trip_id']); base=grouped.get(tid)
  if base is None or base.empty: continue
  start=sec(r.get('start_time')); end=sec(r.get('end_time'))
  try: head=int(float(r.get('headway_secs')))
  except: continue
  if not np.isfinite(start) or not np.isfinite(end) or head<=0: continue
  offset=base.dep_seconds-base.dep_seconds.iloc[0]
  for k,origin in enumerate(range(int(start),int(end),head)):
   x=base.copy(); x['trip_id']=tid+'~F'+str(k); x['dep_seconds']=origin+offset.values; expanded.append(x)
 return pd.concat(expanded,ignore_index=True) if expanded else pd.DataFrame(),freq_rows

def prepare_gtfs():
 inventory=[]; stop_frames=[]; call_frames=[]; trip_frames=[]
 for spec in FEEDS:
  rec={**spec,'retrieved_at':datetime.now(timezone.utc).isoformat(),'download_ok':False,'usable':False,'error':'','bytes':0,'sha256':'','segments':0,
       'service_start':'','service_end':'','active_weekday_services':0,'active_saturday_services':0,'active_weekday_trips':0,'active_saturday_trips':0,'routes':0,'stops':0,'frequency_rows_expanded':0}
  path=FEEDDIR/(spec['id']+'.zip')
  try:
   download(spec['url'],path,240); rec['download_ok']=True; rec['bytes']=path.stat().st_size; rec['sha256']=sha256(path)
   archives=feed_archives(path,spec['id']); rec['segments']=len(archives)
   if not archives: raise ValueError('no usable GTFS archive')
   spans=[]
   for feedseg,z in archives:
    routes=zcsv(z,'routes.txt').fillna(''); trips=zcsv(z,'trips.txt').fillna(''); stops=zcsv(z,'stops.txt').fillna(''); st=zcsv(z,'stop_times.txt').fillna('')
    spans.append(date_span(z)); rec['routes']+=len(routes); rec['stops']+=len(stops)
    route_cols=['route_id','route_type']+[c for c in ['route_short_name','route_long_name'] if c in routes.columns]
    t=trips.merge(routes[route_cols],on='route_id',how='left')
    stopframe=stops[[c for c in ['stop_id','stop_name','stop_lat','stop_lon','location_type','parent_station'] if c in stops.columns]].copy()
    stopframe['feed_id']=spec['id']; stopframe['feed_segment']=feedseg; stopframe['stop_uid']=feedseg+'|'+stopframe.stop_id.astype(str)
    stop_frames.append(stopframe)
    for d,label in [(WEEKDAY,'weekday'),(SATURDAY,'saturday')]:
     active=active_services(z,d)
     if label=='weekday': rec['active_weekday_services']+=len(active)
     else: rec['active_saturday_services']+=len(active)
     calls,nfreq=frequency_expansion(z,t,st,active,feedseg,label); rec['frequency_rows_expanded']+=nfreq
     if calls.empty: continue
     calls=calls.merge(t[[c for c in ['trip_id','route_id','route_type','route_short_name','route_long_name'] if c in t.columns]],on='trip_id',how='left')
     calls=calls[(calls.dep_seconds>=6*3600)&(calls.dep_seconds<24*3600)].copy()
     calls['feed_id']=spec['id']; calls['feed_segment']=feedseg; calls['day']=label
     calls['stop_uid']=feedseg+'|'+calls.stop_id.astype(str)
     calls['trip_uid']=feedseg+'|'+label+'|'+calls.trip_id.astype(str)
     calls['route_uid']=feedseg+'|'+calls.route_id.astype(str)
     calls['operator']=spec['operator']
     calls['mode_group']=[mode_group(spec['id'],a,b) for a,b in zip(calls.route_type,calls.get('route_short_name',pd.Series('',index=calls.index)))]
     keep=['day','feed_id','feed_segment','operator','trip_uid','route_uid','route_type','mode_group','stop_uid','dep_seconds']
     call_frames.append(calls[keep].drop_duplicates())
     tsum=calls[['day','feed_id','feed_segment','operator','trip_uid','route_uid','route_type','mode_group']].drop_duplicates()
     trip_frames.append(tsum)
     if label=='weekday': rec['active_weekday_trips']+=tsum.trip_uid.nunique()
     else: rec['active_saturday_trips']+=tsum.trip_uid.nunique()
   starts=[s[0] for s in spans if s[0]]; ends=[s[1] for s in spans if s[1]]; rec['service_start']=min(starts) if starts else ''; rec['service_end']=max(ends) if ends else ''
   rec['usable']=rec['active_weekday_trips']>0 and rec['active_saturday_trips']>0
  except Exception as e: rec['error']=f'{type(e).__name__}: {e}'
  inventory.append(rec)
 stops=pd.concat(stop_frames,ignore_index=True).drop_duplicates('stop_uid') if stop_frames else pd.DataFrame()
 calls=pd.concat(call_frames,ignore_index=True) if call_frames else pd.DataFrame()
 trips=pd.concat(trip_frames,ignore_index=True).drop_duplicates('trip_uid') if trip_frames else pd.DataFrame()
 pq.write_table(pa.Table.from_pandas(stops,preserve_index=False),PREP/'all_stops.parquet',compression='zstd')
 pq.write_table(pa.Table.from_pandas(calls,preserve_index=False),PREP/'all_calls.parquet',compression='zstd')
 pq.write_table(pa.Table.from_pandas(trips,preserve_index=False),PREP/'all_trips.parquet',compression='zstd')
 pd.DataFrame(inventory).to_csv(OUT/'gtfs_feed_inventory_initial.csv',index=False)
 (OUT/'gtfs_feed_inventory_initial.json').write_text(json.dumps(inventory,indent=2))
 return inventory,stops,calls

def census_and_blocks():
 for k,u in URLS.items():
  ext='.osm.pbf' if k=='osm' else ('.zip' if k=='blocks' else '.csv.gz')
  download(u,DATA/(k+ext),900)
 # ACS tract inputs
 params={'get':'NAME,B01003_001E,B11001_001E,B08201_002E,B08201_003E,B08301_001E,B08301_010E','for':'tract:*','in':'state:34 county:*'}
 url='https://api.census.gov/data/2024/acs/acs5?'+urllib.parse.urlencode(params)
 req=urllib.request.Request(url,headers={'User-Agent':UA})
 with urllib.request.urlopen(req,timeout=180) as r: rows=json.load(r)
 acs=pd.DataFrame(rows[1:],columns=rows[0])
 acs['GEOID']=acs.state+acs.county+acs.tract
 ren={'B01003_001E':'pop_2024','B11001_001E':'households_2024','B08201_002E':'hh_zero_vehicle','B08201_003E':'hh_one_vehicle','B08301_001E':'workers16plus','B08301_010E':'transit_commuters'}
 acs=acs.rename(columns=ren)
 for c in ren.values(): acs[c]=pd.to_numeric(acs[c],errors='coerce')
 acs.to_csv(PREP/'acs_2024_tracts.csv',index=False)
 # Blocks
 bdir=DATA/'blocks_unzip'; bdir.mkdir(exist_ok=True)
 with zipfile.ZipFile(DATA/'blocks.zip') as z: z.extractall(bdir)
 shp=next(bdir.glob('*.shp'))
 blocks=gpd.read_file(shp)
 geoid='GEOID20' if 'GEOID20' in blocks.columns else 'GEOID'
 aland='ALAND20' if 'ALAND20' in blocks.columns else 'ALAND'
 pop='POP20' if 'POP20' in blocks.columns else 'POP'
 housing='HOUSING20' if 'HOUSING20' in blocks.columns else 'HOUSING'
 blocks=blocks[[geoid,aland,pop,housing,'geometry']].rename(columns={geoid:'block_geoid',aland:'aland_m2',pop:'pop20',housing:'housing20'})
 blocks['block_geoid']=blocks.block_geoid.astype(str); blocks['GEOID']=blocks.block_geoid.str[:11]
 blocks['pop20']=pd.to_numeric(blocks.pop20,errors='coerce').fillna(0); blocks['housing20']=pd.to_numeric(blocks.housing20,errors='coerce').fillna(0); blocks['aland_m2']=pd.to_numeric(blocks.aland_m2,errors='coerce').fillna(0)
 # LODES jobs
 lodes=pd.read_csv(DATA/'lodes.csv.gz',compression='gzip',usecols=['w_geocode','C000'],dtype={'w_geocode':str})
 lodes['w_geocode']=lodes.w_geocode.str.zfill(15); lodes['jobs_2023_block']=pd.to_numeric(lodes.C000,errors='coerce').fillna(0)
 blocks=blocks.merge(lodes[['w_geocode','jobs_2023_block']],left_on='block_geoid',right_on='w_geocode',how='left').drop(columns=['w_geocode'])
 blocks['jobs_2023_block']=blocks.jobs_2023_block.fillna(0)
 # Scale decennial block population to ACS tract controls.
 sums=blocks.groupby('GEOID').pop20.sum().rename('tract_pop20')
 blocks=blocks.merge(sums,on='GEOID',how='left').merge(acs[['GEOID','pop_2024','households_2024']],on='GEOID',how='left')
 blocks['pop_scale']=np.where(blocks.tract_pop20>0,blocks.pop_2024/blocks.tract_pop20,np.nan)
 blocks['pop_2024_scaled']=blocks.pop20*blocks.pop_scale
 # Retain resident or job origins. Population in tracts with no 2020 block population remains explicitly unallocated.
 origins=blocks[(blocks.pop_2024_scaled.fillna(0)>0)|(blocks.jobs_2023_block>0)].copy()
 origins=origins.to_crs(26918); origins['origin_geometry']=origins.geometry.representative_point(); origins=origins.set_geometry('origin_geometry')
 origins['x']=origins.geometry.x; origins['y']=origins.geometry.y; origins['block_idx']=np.arange(len(origins),dtype=np.uint32)
 blocks.to_file(PREP/'blocks_inputs.gpkg',layer='blocks',driver='GPKG')
 origins.drop(columns=['geometry'],errors='ignore').to_file(PREP/'origins.gpkg',layer='origins',driver='GPKG')
 return blocks,origins,acs

def edge_allowed(edges):
 def bad(series,vals): return series.fillna('').astype(str).str.lower().isin(vals)
 foot=edges.get('foot',pd.Series('',index=edges.index)).fillna('').astype(str).str.lower()
 access=edges.get('access',pd.Series('',index=edges.index)).fillna('').astype(str).str.lower()
 highway=edges.get('highway',pd.Series('',index=edges.index)).fillna('').astype(str).str.lower()
 explicit=foot.isin(['yes','designated','permissive','destination'])
 ok=~bad(foot,['no','private'])
 ok &= (~bad(access,['no','private']))|explicit
 ok &= (~highway.isin(['motorway','motorway_link','trunk','trunk_link']))|explicit
 ok &= pd.to_numeric(edges.length,errors='coerce').fillna(0)>0
 return ok

def choose_nodes(xy,geoms,tree,node_xy,k=12,max_outside=75):
 d,ix=tree.query(xy,k=k,workers=-1); d=np.atleast_2d(d) if len(xy)==1 else d; ix=np.atleast_2d(ix) if len(xy)==1 else ix
 chosen=np.full(len(xy),-1,dtype=np.int64); snap=np.full(len(xy),np.nan); method=np.full(len(xy),'disconnected',dtype=object)
 for i,g in enumerate(geoms):
  cand=np.atleast_1d(ix[i]); ds=np.atleast_1d(d[i]); gb=g.buffer(1.0)
  for dist,j in zip(ds,cand):
   if gb.covers(Point(float(node_xy[j,0]),float(node_xy[j,1]))): chosen[i]=int(j); snap[i]=float(dist); method[i]='inside_block'; break
  if chosen[i]<0 and float(ds[0])<=max_outside: chosen[i]=int(cand[0]); snap[i]=float(ds[0]); method[i]='short_external_connector'
 return chosen,snap,method

def prepare_network(origins,stops,calls):
 osm=OSM(str(DATA/'osm.osm.pbf')); nodes,edges=osm.get_network(network_type='walking',nodes=True)
 edges=edges[edge_allowed(edges)].copy(); nodes=nodes.to_crs(26918); edges=edges.to_crs(26918)
 # Map OSM IDs to compact graph indices.
 node_ids=nodes.id.astype('int64').to_numpy(); order=np.argsort(node_ids); sorted_ids=node_ids[order]
 u_pos=np.searchsorted(sorted_ids,edges.u.astype('int64').to_numpy()); v_pos=np.searchsorted(sorted_ids,edges.v.astype('int64').to_numpy())
 valid=(u_pos<len(sorted_ids))&(v_pos<len(sorted_ids))&(sorted_ids[np.minimum(u_pos,len(sorted_ids)-1)]==edges.u.astype('int64').to_numpy())&(sorted_ids[np.minimum(v_pos,len(sorted_ids)-1)]==edges.v.astype('int64').to_numpy())
 edges=edges.iloc[np.where(valid)[0]].copy(); u=order[u_pos[valid]].astype(np.uint32); v=order[v_pos[valid]].astype(np.uint32); length=pd.to_numeric(edges.length,errors='coerce').to_numpy(dtype=np.float32)
 # Undirected pedestrian graph; duplicate arcs are harmless for shortest paths.
 src=np.concatenate([u,v]); dst=np.concatenate([v,u]); wt=np.concatenate([length,length]); idx=np.argsort(src,kind='mergesort'); src=src[idx]; dst=dst[idx]; wt=wt[idx]
 offsets=np.zeros(len(nodes)+1,dtype=np.uint64); np.add.at(offsets,src.astype(np.int64)+1,1); np.cumsum(offsets,out=offsets)
 offsets.tofile(PREP/'offsets.bin'); dst.astype(np.uint32).tofile(PREP/'neighbors.bin'); wt.astype(np.float32).tofile(PREP/'weights.bin')
 node_xy=np.column_stack([nodes.geometry.x.to_numpy(),nodes.geometry.y.to_numpy()]); np.save(PREP/'node_xy.npy',node_xy)
 tree=cKDTree(node_xy)
 # Block origins: prefer a graph node inside the block. A very short external connector is retained and reported.
 oxy=origins[['x','y']].to_numpy(); chosen,snap,method=choose_nodes(oxy,origins.geometry.tolist(),tree,node_xy)
 origins=origins.copy(); origins['graph_node']=chosen; origins['origin_snap_m']=snap; origins['snap_method']=method; origins['connected']=chosen>=0
 # Stop nodes. Stop coordinates are producer-supplied; rail stops receive a larger snap tolerance for platforms and station approaches.
 st=stops.copy(); st['stop_lat']=pd.to_numeric(st.stop_lat,errors='coerce'); st['stop_lon']=pd.to_numeric(st.stop_lon,errors='coerce'); st=st.dropna(subset=['stop_lat','stop_lon'])
 transformer=Transformer.from_crs(4326,26918,always_xy=True); sx,sy=transformer.transform(st.stop_lon.to_numpy(),st.stop_lat.to_numpy()); sxy=np.column_stack([sx,sy]); sd,si=tree.query(sxy,k=1,workers=-1)
 st['graph_node']=si.astype(np.int64); st['stop_snap_m']=sd.astype(float)
 active_stop_modes=calls[['stop_uid','mode_group']].drop_duplicates(); st=st.merge(active_stop_modes,on='stop_uid',how='inner')
 st['snap_limit_m']=np.where(st.mode_group.eq('bus'),150.0,300.0); st['matched']=st.stop_snap_m<=st.snap_limit_m
 # One source record per unique graph node. Calls remain linked by stop_uid and acquire source_idx below.
 srcnodes=np.sort(st.loc[st.matched,'graph_node'].unique()).astype(np.uint32); source_lookup={int(n):i for i,n in enumerate(srcnodes)}
 st['source_idx']=st.graph_node.map(source_lookup); st['source_idx']=st.source_idx.fillna(-1).astype(np.int64)
 origins_connected=origins[origins.connected].copy().reset_index(drop=True); origins_connected['reach_block_idx']=np.arange(len(origins_connected),dtype=np.uint32)
 origins_connected.graph_node.astype(np.uint32).to_numpy().tofile(PREP/'block_nodes.bin'); srcnodes.tofile(PREP/'sources.bin')
 # Persist mappings.
 pq.write_table(pa.Table.from_pandas(origins,preserve_index=False),PREP/'origins_all.parquet',compression='zstd')
 pq.write_table(pa.Table.from_pandas(origins_connected,preserve_index=False),PREP/'origins_connected.parquet',compression='zstd')
 pq.write_table(pa.Table.from_pandas(st,preserve_index=False),PREP/'stops_snapped.parquet',compression='zstd')
 calls2=calls.merge(st[['stop_uid','source_idx','stop_snap_m','matched']],on='stop_uid',how='left'); calls2=calls2[calls2.matched.fillna(False)&(calls2.source_idx>=0)].copy()
 pq.write_table(pa.Table.from_pandas(calls2,preserve_index=False),PREP/'calls_matched.parquet',compression='zstd')
 # Reachability on the actual OSM pedestrian graph.
 subprocess.run(['g++','-O3','-std=c++17','-fopenmp','pipeline/bounded_reach.cpp','-o',str(PREP/'bounded_reach')],check=True)
 env=os.environ.copy(); env['OMP_NUM_THREADS']=env.get('OMP_NUM_THREADS','4')
 subprocess.run([str(PREP/'bounded_reach'),str(PREP/'offsets.bin'),str(PREP/'neighbors.bin'),str(PREP/'weights.bin'),str(PREP/'block_nodes.bin'),str(PREP/'sources.bin'),'1200',str(PREP/'reach.bin')],check=True,env=env)
 dtype=np.dtype([('reach_block_idx','<u4'),('source_idx','<u4'),('network_m','<f4')]); arr=np.fromfile(PREP/'reach.bin',dtype=dtype)
 reach=pd.DataFrame({n:arr[n] for n in arr.dtype.names}); pq.write_table(pa.Table.from_pandas(reach,preserve_index=False),PREP/'reachability.parquet',compression='zstd')
 # Compact network metadata and QA samples.
 meta={'retrieved_at':datetime.now(timezone.utc).isoformat(),'osm_url':URLS['osm'],'osm_sha256':sha256(DATA/'osm.osm.pbf'),'raw_nodes':int(len(nodes)),'filtered_edges':int(len(edges)),'directed_arcs':int(len(dst)),
       'origin_count':int(len(origins)),'connected_origins':int(origins.connected.sum()),'external_connector_origins':int((origins.snap_method=='short_external_connector').sum()),
       'active_stops':int(st.stop_uid.nunique()),'matched_active_stops':int(st.loc[st.matched,'stop_uid'].nunique()),'unique_stop_nodes':int(len(srcnodes)),'reachability_pairs':int(len(reach))}
 (OUT/'pedestrian_network_metadata.json').write_text(json.dumps(meta,indent=2))
 return origins,origins_connected,st,calls2,reach,meta

def main():
 inv,stops,calls=prepare_gtfs(); blocks,origins,acs=census_and_blocks(); origins_all,origins_connected,stops_snapped,calls2,reach,meta=prepare_network(origins,stops,calls)
 source_rows=[{'dataset':'OpenStreetMap New Jersey extract','url':URLS['osm'],'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':sha256(DATA/'osm.osm.pbf')},
              {'dataset':'2020 Census TIGER/Line blocks','url':URLS['blocks'],'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':sha256(DATA/'blocks.zip')},
              {'dataset':'2023 LODES workplace area characteristics','url':URLS['lodes'],'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':sha256(DATA/'lodes.csv.gz')},
              {'dataset':'2024 ACS 5-year tract estimates','url':'https://api.census.gov/data/2024/acs/acs5','retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':''}]
 pd.DataFrame(source_rows).to_csv(OUT/'source_register_core.csv',index=False)
 print(json.dumps({'feeds':len(inv),'calls':len(calls2),'origins':len(origins_connected),'reach_pairs':len(reach),**meta},indent=2))

if __name__=='__main__': main()
