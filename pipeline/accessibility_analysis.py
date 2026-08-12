#!/usr/bin/env python3
from __future__ import annotations

import csv
import gc
import gzip
import hashlib
import io
import json
import math
import os
import pathlib
import shutil
import sys
import time
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import geopandas as gpd
from pyproj import Transformer
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from pyrosm import OSM
from pyroaring import BitMap

ROOT = pathlib.Path('.')
OUT = ROOT / 'out'
WORK = ROOT / 'work'
DATA = WORK / 'data'
FEEDDIR = WORK / 'feeds'
for p in (OUT, DATA, FEEDDIR):
    p.mkdir(parents=True, exist_ok=True)

UA = 'NJ-Transit-Score-Accessible-Service/2.0 (public-interest research)'
TUESDAY = date(2026, 8, 18)
SATURDAY = date(2026, 8, 15)
RETRIEVED_AT = datetime.now(timezone.utc).isoformat()
PERIODS = {
    'am_peak': (6 * 3600, 9 * 3600),
    'midday': (9 * 3600, 15 * 3600),
    'pm_peak': (15 * 3600, 19 * 3600),
    'evening': (19 * 3600, 24 * 3600),
}
HOUR_START = 6
HOUR_END = 24
PRIMARY_BUS = 400.0
PRIMARY_RAIL = 800.0
SENS_BUS = 800.0
SENS_RAIL = 1200.0
MAX_PATH = 1200.0
ORIGIN_SNAP_MAX = 300.0
STOP_SNAP_MAX = 250.0
SUSTAINED_HOURS = 6

DATA_URLS = {
    'blocks': 'https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_34_tabblock20.zip',
    'tracts': 'https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_34_tract.zip',
    'states': 'https://www2.census.gov/geo/tiger/TIGER2024/STATE/tl_2024_us_state.zip',
    'lodes': 'https://lehd.ces.census.gov/data/lodes/LODES8/nj/wac/nj_wac_S000_JT00_2023.csv.gz',
    'osm': 'https://download.geofabrik.de/north-america/us/new-jersey-latest.osm.pbf',
    'acs': 'https://api.census.gov/data/2024/acs/acs5?get=NAME,B01003_001E&for=tract:*&in=state:34',
}

FEEDS = [
    {'id':'njt_bus','operator':'NJ TRANSIT Bus','url':'https://www.njtransit.com/bus_data.zip','authority':'NJ TRANSIT','modes':'bus','priority':'statewide'},
    {'id':'njt_rail','operator':'NJ TRANSIT Rail and Light Rail','url':'https://www.njtransit.com/rail_data.zip','authority':'NJ TRANSIT','modes':'commuter rail; light rail; hybrid rail','priority':'statewide'},
    {'id':'path','operator':'PATH','url':'https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/14843/PATHGTFS.zip','authority':'FTA National RTAP / PATH','modes':'heavy rail','priority':'regional'},
    {'id':'patco','operator':'PATCO','url':'https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/13562/PATCO_GTFS.zip','authority':'FTA National RTAP / PATCO','modes':'heavy rail','priority':'regional'},
    {'id':'academy','operator':'Academy Lines','url':'https://www.njtransit.com/Academy_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'commuter bus','priority':'regional'},
    {'id':'coachusa','operator':'Coach USA New Jersey services','url':'https://api.prod.coachusa.com/gtfs','authority':'FTA GTFS inventory / Coach USA','modes':'commuter bus','priority':'regional'},
    {'id':'lakeland','operator':'Lakeland Bus Lines','url':'https://content.njtransit.com/sites/default/files/developers-resources/LakelandBusLines_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'commuter bus','priority':'regional'},
    {'id':'nywaterway_ferry','operator':'NY Waterway Ferry','url':'https://nywaterway.connexionz.net/rtt/public/resource/gtfs.zip','authority':'FTA GTFS inventory / NY Waterway','modes':'ferry','priority':'regional'},
    {'id':'nywaterway_bus','operator':'NY Waterway Shuttle Bus','url':'https://services.saucontds.com/service-schedule-server/gtfsFeed/749f33f0-b1d7-4be2-b0ea-3f63cf39073e','authority':'FTA GTFS inventory / NY Waterway','modes':'bus','priority':'regional'},
    {'id':'seastreak','operator':'Seastreak','url':'https://seastreak.com/api/transit/google_transit.zip','authority':'FTA GTFS inventory / Seastreak','modes':'ferry','priority':'regional'},
    {'id':'boxcar','operator':'Boxcar','url':'https://boxcar-gtfs.vercel.app/api/gtfs','authority':'Mobility Database / Boxcar','modes':'commuter bus','priority':'regional'},
    {'id':'amtrak','operator':'Amtrak','url':'https://content.amtrak.com/content/gtfs/GTFS.zip','authority':'Amtrak','modes':'intercity rail','priority':'regional'},
    {'id':'septa','operator':'SEPTA','url':'https://www3.septa.org/developer/gtfs_public.zip','authority':'SEPTA','modes':'regional rail; bus; metro','priority':'regional'},
    {'id':'gloucester','operator':'Gloucester County','url':'https://www.njtransit.com/Gloucester_Co_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','priority':'local'},
    {'id':'atlantic','operator':'Atlantic County','url':'https://www.njtransit.com/AtlanticCo_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','priority':'local'},
    {'id':'sjta','operator':'South Jersey Transportation Authority','url':'https://www.njtransit.com/SJTA_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','priority':'local'},
    {'id':'cumberland','operator':'Cumberland County','url':'https://www.njtransit.com/Cumberland_Co_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','priority':'local'},
    {'id':'burlington','operator':'Burlington County Shuttles','url':'https://www.njtransit.com/BurlingtonShuttles_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','priority':'local'},
    {'id':'somerset','operator':'Somerset County','url':'https://www.njtransit.com/SomersetCounty_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','priority':'local'},
    {'id':'hunterdon','operator':'Hunterdon LINK','url':'https://www.njtransit.com/Hunterdon_Co_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','priority':'local'},
    {'id':'warren','operator':'Warren County','url':'https://www.njtransit.com/WCT_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','priority':'local'},
    {'id':'sussex','operator':'Sussex County','url':'https://www.njtransit.com/sussexcounty_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','priority':'local'},
]

OMISSIONS = [
    {'operator':'Broadway Bus Corporation','reason':'The public GTFS file retrieved from NJ TRANSIT expired on 2022-12-31 and was not used for 2026 service.'},
    {'operator':'Atlantic City Jitney Association','reason':'No usable current public static GTFS feed was identified in the FTA National Transit Map inventory or Mobility Database catalog at retrieval.'},
    {'operator':'Rutgers University campus bus','reason':'No usable current public static GTFS feed was identified in the audited national feed inventories at retrieval.'},
    {'operator':'Princeton TigerTransit','reason':'No usable current public static GTFS feed was identified in the audited national feed inventories at retrieval.'},
    {'operator':'Informal/private jitney services','reason':'No complete authoritative public GTFS inventory exists; these services are excluded.'},
    {'operator':'Demand-response and paratransit','reason':'Not fixed-route scheduled service and outside the analysis definition.'},
]

def log(msg):
    print(f'[{datetime.now(timezone.utc).isoformat()}] {msg}', flush=True)

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def download(url,path,timeout=600):
    if path.exists() and path.stat().st_size>0: return {'bytes':path.stat().st_size,'sha256':sha256(path)}
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=timeout) as r, open(path,'wb') as f:
        while True:
            b=r.read(1<<20)
            if not b: break
            f.write(b)
    return {'bytes':path.stat().st_size,'sha256':sha256(path)}

def parse_hms(v):
    try:
        p=str(v).split(':'); return int(p[0])*3600+int(p[1])*60+int(float(p[2]))
    except Exception: return -1

def route_mode(rt):
    try: x=int(float(rt))
    except Exception: x=3
    if x==4 or x in (0,1,2,5,6,7) or 100<=x<400: return 'rail'
    return 'bus'

def read_txt(z,name,dtype=None,usecols=None):
    if name not in z.namelist(): return pd.DataFrame()
    return pd.read_csv(z.open(name),dtype=dtype,usecols=usecols,low_memory=False,encoding='utf-8-sig')

def active_services(z,day):
    ds=day.strftime('%Y%m%d'); wd=day.strftime('%A').lower(); active=set()
    cal=read_txt(z,'calendar.txt',dtype=str)
    if not cal.empty:
        mask=(cal['start_date']<=ds)&(cal['end_date']>=ds)&(cal.get(wd,'0')=='1')
        active.update(cal.loc[mask,'service_id'].astype(str))
    exc=read_txt(z,'calendar_dates.txt',dtype=str)
    if not exc.empty:
        for r in exc.loc[exc['date']==ds].itertuples(index=False):
            sid=str(getattr(r,'service_id')); et=str(getattr(r,'exception_type'))
            if et=='1': active.add(sid)
            elif et=='2': active.discard(sid)
    return active

def calendar_span(z):
    starts=[]; ends=[]
    cal=read_txt(z,'calendar.txt',dtype=str)
    if not cal.empty:
        starts.extend(cal['start_date'].dropna().astype(str)); ends.extend(cal['end_date'].dropna().astype(str))
    exc=read_txt(z,'calendar_dates.txt',dtype=str)
    if not exc.empty:
        starts.extend(exc['date'].dropna().astype(str)); ends.extend(exc['date'].dropna().astype(str))
    return (min(starts) if starts else '',max(ends) if ends else '')

def iter_segments(spec,path):
    outer=zipfile.ZipFile(path); names=set(outer.namelist()); required={'stops.txt','routes.txt','trips.txt','stop_times.txt'}
    if required.issubset(names):
        yield spec['id'],'',outer; return
    for n in [n for n in outer.namelist() if n.lower().endswith('.zip')]:
        try:
            inner=zipfile.ZipFile(io.BytesIO(outer.read(n)))
            if required.issubset(set(inner.namelist())):
                suffix=pathlib.Path(n).stem.lower().replace('google_','')
                yield f"{spec['id']}_{suffix}",n,inner
        except Exception: continue

@dataclass
class StopService:
    uid:str; operator:str; mode:str; lon:float; lat:float; tue_all:BitMap; sat_all:BitMap; tue_periods:list; tue_hours:list; sat_hours:list; tue_bus_hours:list; tue_rail_hours:list; sat_bus_hours:list; sat_rail_hours:list

def empty_stop(uid,operator,mode,lon,lat):
    return StopService(uid,operator,mode,lon,lat,BitMap(),BitMap(),[BitMap() for _ in PERIODS],[BitMap() for _ in range(18)],[BitMap() for _ in range(18)],[BitMap() for _ in range(18)],[BitMap() for _ in range(18)],[BitMap() for _ in range(18)],[BitMap() for _ in range(18)])

def add_group_bitmaps(df,services,daytype):
    if df.empty:return
    for stop_idx,grp in df.groupby('stop_idx',sort=False):
        s=services[int(stop_idx)]; allbm=BitMap(grp['trip_int'].drop_duplicates().astype(np.uint32).tolist())
        if daytype=='tue':s.tue_all|=allbm
        else:s.sat_all|=allbm
        if daytype=='tue':
            for pi,(_,ab) in enumerate(PERIODS.items()):
                a,b=ab; vals=grp.loc[(grp['sec']>=a)&(grp['sec']<b),'trip_int'].drop_duplicates()
                if len(vals):s.tue_periods[pi]|=BitMap(vals.astype(np.uint32).tolist())
        for h in range(6,24):
            vals=grp.loc[grp['hour']==h]
            if vals.empty:continue
            bm=BitMap(vals['trip_int'].drop_duplicates().astype(np.uint32).tolist()); busv=vals.loc[vals['mode']=='bus','trip_int'].drop_duplicates(); railv=vals.loc[vals['mode']=='rail','trip_int'].drop_duplicates(); j=h-6
            if daytype=='tue':
                s.tue_hours[j]|=bm
                if len(busv):s.tue_bus_hours[j]|=BitMap(busv.astype(np.uint32).tolist())
                if len(railv):s.tue_rail_hours[j]|=BitMap(railv.astype(np.uint32).tolist())
            else:
                s.sat_hours[j]|=bm
                if len(busv):s.sat_bus_hours[j]|=BitMap(busv.astype(np.uint32).tolist())
                if len(railv):s.sat_rail_hours[j]|=BitMap(railv.astype(np.uint32).tolist())

def process_day(z,segment_id,routes,trips,stops_map,services,day,daytype,trip_counter):
    active=active_services(z,day)
    if not active:return trip_counter,0
    ta=trips.loc[trips['service_id'].astype(str).isin(active)].copy()
    if ta.empty:return trip_counter,0
    ta=ta.merge(routes[['route_id','route_type']],on='route_id',how='left')
    if segment_id.startswith('amtrak'):ta=ta.loc[ta['route_type'].astype(str).str.replace('.0','',regex=False)=='2'].copy()
    if ta.empty:return trip_counter,0
    trip_ids=ta['trip_id'].astype(str).tolist(); trip_ints=np.arange(trip_counter,trip_counter+len(trip_ids),dtype=np.uint32); trip_counter+=len(trip_ids)
    tripmap=pd.DataFrame({'trip_id':trip_ids,'trip_int':trip_ints,'route_type':ta['route_type'].values})
    st=read_txt(z,'stop_times.txt',dtype={'trip_id':str,'stop_id':str,'departure_time':str,'arrival_time':str})
    st=st.loc[st['trip_id'].isin(set(trip_ids)),['trip_id','stop_id','departure_time','arrival_time']]
    if st.empty:return trip_counter,len(trip_ids)
    st['sec']=st['departure_time'].map(parse_hms); bad=st['sec']<0
    if bad.any():st.loc[bad,'sec']=st.loc[bad,'arrival_time'].map(parse_hms)
    st=st.loc[(st['sec']>=21600)&(st['sec']<86400)].copy(); st['hour']=(st['sec']//3600).astype(np.int16)
    st=st.merge(tripmap,on='trip_id',how='inner'); st['mode']=st['route_type'].map(route_mode); st['stop_uid']=segment_id+':'+st['stop_id'].astype(str); st['stop_idx']=st['stop_uid'].map(stops_map); st=st.dropna(subset=['stop_idx']); st['stop_idx']=st['stop_idx'].astype(np.int32)
    add_group_bitmaps(st[['stop_idx','trip_int','sec','hour','mode']],services,daytype)
    return trip_counter,len(trip_ids)

def prepare_gtfs(nj_polygon):
    services=[]; stop_index={}; inventory=[]; sources=[]; trip_counter_tue=0; trip_counter_sat=0
    for spec in FEEDS:
        path=FEEDDIR/f"{spec['id']}.zip"; rec=dict(spec); rec.update({'retrieval_date':RETRIEVED_AT,'download_ok':False,'sha256':'','bytes':0,'segments':0,'service_start':'','service_end':'','tuesday_active_trips':0,'saturday_active_trips':0,'stop_count':0,'nj_or_near_stop_count':0,'included':False,'exclusion_reason':'','errors':''})
        try:
            meta=download(spec['url'],path);rec.update({'download_ok':True,**meta})
            for segment_id,nested_name,z in iter_segments(spec,path):
                rec['segments']+=1;span=calendar_span(z)
                if span[0] and (not rec['service_start'] or span[0]<rec['service_start']):rec['service_start']=span[0]
                if span[1] and (not rec['service_end'] or span[1]>rec['service_end']):rec['service_end']=span[1]
                routes=read_txt(z,'routes.txt',dtype={'route_id':str,'route_type':str});trips=read_txt(z,'trips.txt',dtype=str);stops=read_txt(z,'stops.txt',dtype={'stop_id':str,'stop_lat':float,'stop_lon':float})
                if routes.empty or trips.empty or stops.empty:continue
                rec['stop_count']+=len(stops);sg=gpd.GeoDataFrame(stops.copy(),geometry=gpd.points_from_xy(stops.stop_lon,stops.stop_lat),crs=4326);near=sg.geometry.within(nj_polygon.buffer(.03));rec['nj_or_near_stop_count']+=int(near.sum())
                route_modes=set(routes['route_type'].map(route_mode));default_mode='rail' if route_modes=={'rail'} else ('bus' if route_modes=={'bus'} else 'mixed')
                for r in stops.loc[near].itertuples(index=False):
                    uid=segment_id+':'+str(r.stop_id)
                    if uid not in stop_index:
                        stop_index[uid]=len(services);services.append(empty_stop(uid,spec['operator'],default_mode,float(r.stop_lon),float(r.stop_lat)))
                trip_counter_tue,tcnt=process_day(z,segment_id,routes,trips,stop_index,services,TUESDAY,'tue',trip_counter_tue);trip_counter_sat,scnt=process_day(z,segment_id,routes,trips,stop_index,services,SATURDAY,'sat',trip_counter_sat);rec['tuesday_active_trips']+=tcnt;rec['saturday_active_trips']+=scnt
            rec['included']=rec['download_ok'] and rec['segments']>0 and rec['nj_or_near_stop_count']>0 and (rec['tuesday_active_trips']>0 or rec['saturday_active_trips']>0)
            if not rec['included']:
                if rec['segments']==0:rec['exclusion_reason']='Downloaded object did not contain a usable GTFS schedule.'
                elif rec['nj_or_near_stop_count']==0:rec['exclusion_reason']='No stop was located in or near New Jersey.'
                else:rec['exclusion_reason']='No active trips on the representative dates.'
        except Exception as e:
            rec['errors']=f'{type(e).__name__}: {e}';rec['exclusion_reason']='Feed could not be downloaded or parsed.'
        inventory.append(rec);sources.append({'source_id':f'GTFS-{spec["id"]}','dataset':spec['operator']+' GTFS','publisher':spec['authority'],'url':spec['url'],'retrieved_at':RETRIEVED_AT,'sha256':rec['sha256'],'role':'scheduled fixed-route service'});log(f"GTFS {spec['id']}: included={rec['included']} Tue={rec['tuesday_active_trips']} Sat={rec['saturday_active_trips']} stops={rec['nj_or_near_stop_count']}")
    services=[s for s in services if len(s.tue_all) or len(s.sat_all)]
    for s in services:
        has_bus=any(len(x) for x in s.tue_bus_hours+s.sat_bus_hours);has_rail=any(len(x) for x in s.tue_rail_hours+s.sat_rail_hours);s.mode='mixed' if has_bus and has_rail else ('rail' if has_rail else 'bus')
    return services,inventory,sources

def load_blocks_and_jobs():
    paths={'blocks':DATA/'blocks.zip','tracts':DATA/'tracts.zip','states':DATA/'states.zip','lodes':DATA/'lodes.csv.gz','osm':DATA/'new-jersey.osm.pbf'};meta={}
    for k,u in DATA_URLS.items():
        if k=='acs':continue
        meta[k]=download(u,paths[k]);log(f'downloaded {k}: {meta[k]["bytes"]:,} bytes')
    states=gpd.read_file(paths['states']);nj=states.loc[states['STUSPS']=='NJ'].to_crs(4326).geometry.iloc[0];blocks=gpd.read_file(paths['blocks']);geoid_col=next(c for c in ['GEOID20','GEOID'] if c in blocks.columns);pop_col=next((c for c in ['POP20','POP100'] if c in blocks.columns),None);lon_col=next((c for c in ['INTPTLON20','INTPTLON'] if c in blocks.columns),None);lat_col=next((c for c in ['INTPTLAT20','INTPTLAT'] if c in blocks.columns),None)
    blocks['GEOID20']=blocks[geoid_col].astype(str).str.zfill(15);blocks['tract_geoid']=blocks.GEOID20.str[:11]
    if pop_col is None:raise RuntimeError('TIGER block file lacks POP20')
    blocks['pop2020']=pd.to_numeric(blocks[pop_col],errors='coerce').fillna(0.)
    if lon_col and lat_col:blocks['lon']=pd.to_numeric(blocks[lon_col],errors='coerce');blocks['lat']=pd.to_numeric(blocks[lat_col],errors='coerce')
    else:
        pts=blocks.geometry.representative_point().to_crs(4326);blocks['lon']=pts.x;blocks['lat']=pts.y
    req=urllib.request.Request(DATA_URLS['acs'],headers={'User-Agent':UA});acs_raw=json.load(urllib.request.urlopen(req,timeout=180));acs=pd.DataFrame(acs_raw[1:],columns=acs_raw[0]);acs['tract_geoid']=acs.state+acs.county+acs.tract;acs['pop2024']=pd.to_numeric(acs.B01003_001E,errors='coerce').clip(lower=0);blocks=blocks.merge(acs[['tract_geoid','pop2024']],on='tract_geoid',how='left');popsum=blocks.groupby('tract_geoid').pop2020.transform('sum');blocks['pop_scaled_2024']=np.where(popsum>0,blocks.pop2020/popsum*blocks.pop2024.fillna(0),0.);zero_alloc=[]
    for tract,idx in blocks.loc[(popsum==0)&(blocks.pop2024.fillna(0)>0)].groupby('tract_geoid').groups.items():
        chosen=blocks.loc[idx].geometry.to_crs(26918).area.idxmax();blocks.loc[chosen,'pop_scaled_2024']=float(blocks.loc[chosen,'pop2024']);zero_alloc.append({'tract_geoid':tract,'allocated_population':float(blocks.loc[chosen,'pop2024']),'block_geoid':blocks.loc[chosen,'GEOID20']})
    lodes=pd.read_csv(paths['lodes'],compression='gzip',dtype={'w_geocode':str},usecols=['w_geocode','C000']);lodes['GEOID20']=lodes.w_geocode.astype(str).str.zfill(15);jobs=lodes.groupby('GEOID20',as_index=False).C000.sum().rename(columns={'C000':'jobs_2023_block'});blocks=blocks.merge(jobs,on='GEOID20',how='left');blocks['jobs_2023_block']=blocks.jobs_2023_block.fillna(0.);origins=blocks.loc[(blocks.pop_scaled_2024>0)|(blocks.jobs_2023_block>0),['GEOID20','tract_geoid','pop2020','pop_scaled_2024','jobs_2023_block','lon','lat']].copy();recon={'block_count_total':int(len(blocks)),'origin_block_count':int(len(origins)),'pop2020_total':float(blocks.pop2020.sum()),'acs2024_total':float(acs.pop2024.sum()),'scaled_block_population_total':float(origins.pop_scaled_2024.sum()),'lodes_jobs_total':float(lodes.C000.sum()),'origin_jobs_total':float(origins.jobs_2023_block.sum()),'zero_population_base_tract_allocations':zero_alloc,'acs_missing_tract_blocks':int(blocks.pop2024.isna().sum()),'lodes_unmatched_rows':int((~lodes.GEOID20.isin(set(blocks.GEOID20))).sum())};sources=[{'source_id':'CENSUS-BLOCKS','dataset':'2020 TIGER/Line Census Blocks','publisher':'U.S. Census Bureau','url':DATA_URLS['blocks'],'retrieved_at':RETRIEVED_AT,'sha256':meta['blocks']['sha256'],'role':'block geography, interior points, 2020 population'},{'source_id':'ACS-2024','dataset':'2020–2024 ACS 5-year B01003','publisher':'U.S. Census Bureau','url':DATA_URLS['acs'],'retrieved_at':RETRIEVED_AT,'sha256':'','role':'2024 tract population controls'},{'source_id':'LODES-2023','dataset':'LODES8 WAC S000 JT00 2023','publisher':'U.S. Census Bureau LEHD','url':DATA_URLS['lodes'],'retrieved_at':RETRIEVED_AT,'sha256':meta['lodes']['sha256'],'role':'block workplace employment'},{'source_id':'OSM','dataset':'OpenStreetMap New Jersey extract','publisher':'OpenStreetMap contributors / Geofabrik','url':DATA_URLS['osm'],'retrieved_at':RETRIEVED_AT,'sha256':meta['osm']['sha256'],'role':'pedestrian routing network'}]
    return origins.reset_index(drop=True),nj,recon,sources,paths

def prepare_network(osm_path,origin_xy,stop_xy):
    log('loading OpenStreetMap pedestrian network');osm=OSM(str(osm_path));nodes,edges=osm.get_network(network_type='walking',nodes=True);log(f'raw OSM walking network: {len(nodes):,} nodes, {len(edges):,} edges');mask=np.ones(len(edges),dtype=bool)
    for col in ('access','foot'):
        if col in edges.columns:mask&=~edges[col].astype(str).str.lower().isin({'no','private'}).to_numpy()
    if 'highway' in edges.columns:mask&=~edges.highway.astype(str).str.lower().isin({'motorway','motorway_link','trunk','trunk_link','raceway','construction','proposed'}).to_numpy()
    if 'motorroad' in edges.columns:mask&=edges.motorroad.astype(str).str.lower().ne('yes').to_numpy()
    edges=edges.loc[mask].copy();node_ids=nodes.id.astype(np.int64).to_numpy();lons=nodes.lon.astype(float).to_numpy() if 'lon' in nodes.columns else nodes.geometry.x.to_numpy();lats=nodes.lat.astype(float).to_numpy() if 'lat' in nodes.columns else nodes.geometry.y.to_numpy();trans=Transformer.from_crs(4326,26918,always_xy=True);nx,ny=trans.transform(lons,lats);eu=edges.u.astype(np.int64).to_numpy();ev=edges.v.astype(np.int64).to_numpy();el=pd.to_numeric(edges.length,errors='coerce').to_numpy(float);valid=np.isfinite(el)&(el>0);eu=eu[valid];ev=ev[valid];el=el[valid];order=np.argsort(node_ids);sorted_ids=node_ids[order];up=np.searchsorted(sorted_ids,eu);vp=np.searchsorted(sorted_ids,ev);upc=np.minimum(up,len(sorted_ids)-1);vpc=np.minimum(vp,len(sorted_ids)-1);match=(up<len(sorted_ids))&(vp<len(sorted_ids))&(sorted_ids[upc]==eu)&(sorted_ids[vpc]==ev);ui=order[up[match]].astype(np.int32);vi=order[vp[match]].astype(np.int32);el=el[match].astype(np.float32);stats={'raw_nodes':int(len(nodes)),'raw_edges':int(len(mask)),'filtered_edges':int(len(el)),'removed_edges':int((~mask).sum()),'edge_id_unmatched':int((~match).sum())};del nodes,edges,osm,eu,ev,sorted_ids,order,up,vp;gc.collect();tree=cKDTree(np.column_stack([nx,ny]));od,on=tree.query(origin_xy,k=1,workers=-1);sd,sn=tree.query(stop_xy,k=1,workers=-1);del tree;gc.collect();return lons,lats,np.asarray(nx),np.asarray(ny),ui,vi,el,on.astype(np.int32),od.astype(np.float32),sn.astype(np.int32),sd.astype(np.float32),stats

def union_metrics(reach,services,sensitivity=False):
    selected=[]
    for si,dist in reach:
        s=services[si];limit=(SENS_BUS if sensitivity else PRIMARY_BUS) if s.mode=='bus' else (SENS_RAIL if sensitivity else PRIMARY_RAIL)
        if dist<=limit:selected.append(si)
    ta=BitMap();sa=BitMap();tp=[BitMap() for _ in range(4)];th=[BitMap() for _ in range(18)];sh=[BitMap() for _ in range(18)];tb=[BitMap() for _ in range(18)];tr=[BitMap() for _ in range(18)];sb=[BitMap() for _ in range(18)];sr=[BitMap() for _ in range(18)]
    for si in selected:
        s=services[si];ta|=s.tue_all;sa|=s.sat_all
        for i in range(4):tp[i]|=s.tue_periods[i]
        for i in range(18):th[i]|=s.tue_hours[i];sh[i]|=s.sat_hours[i];tb[i]|=s.tue_bus_hours[i];tr[i]|=s.tue_rail_hours[i];sb[i]|=s.sat_bus_hours[i];sr[i]|=s.sat_rail_hours[i]
    c=np.array([len(x) for x in th]);sc=np.array([len(x) for x in sh]);bc=np.array([len(x) for x in tb]);rc=np.array([len(x) for x in tr]);sbc=np.array([len(x) for x in sb]);src=np.array([len(x) for x in sr]);return {'wd_departures':len(ta),'wd_am_departures':len(tp[0]),'wd_midday_departures':len(tp[1]),'wd_pm_departures':len(tp[2]),'wd_evening_departures':len(tp[3]),'sat_departures':len(sa),'wd_useful_hours_15':int((c>=4).sum()),'wd_useful_hours_30':int((c>=2).sum()),'wd_useful_hours_60':int((c>=1).sum()),'sat_useful_hours_15':int((sc>=4).sum()),'sat_useful_hours_30':int((sc>=2).sum()),'sat_useful_hours_60':int((sc>=1).sum()),'wd_access_15':int((c>=4).sum()>=SUSTAINED_HOURS),'wd_access_30':int((c>=2).sum()>=SUSTAINED_HOURS),'wd_access_60':int((c>=1).sum()>=SUSTAINED_HOURS),'sat_access_15':int((sc>=4).sum()>=SUSTAINED_HOURS),'sat_access_30':int((sc>=2).sum()>=SUSTAINED_HOURS),'sat_access_60':int((sc>=1).sum()>=SUSTAINED_HOURS),'wd_rail_access':int(rc.sum()>0),'wd_frequent_bus_access':int((bc>=4).sum()>=SUSTAINED_HOURS),'wd_any_access':int(len(ta)>0),'sat_rail_access':int(src.sum()>0),'sat_frequent_bus_access':int((sbc>=4).sum()>=SUSTAINED_HOURS),'sat_any_access':int(len(sa)>0),'reachable_stop_count':len(selected),'raw_reachable_stop_calls_proxy':sum(len(services[si].tue_all) for si in selected)}

def build_tile_graph(node_mask,u_idx,v_idx,lengths,local_map):
    ng=np.flatnonzero(node_mask).astype(np.int32);local_map[ng]=np.arange(len(ng),dtype=np.int32);em=node_mask[u_idx]&node_mask[v_idx];lu=local_map[u_idx[em]];lv=local_map[v_idx[em]];ll=lengths[em];valid=lu!=lv;lu=lu[valid];lv=lv[valid];ll=ll[valid];a=np.minimum(lu,lv).astype(np.int64);b=np.maximum(lu,lv).astype(np.int64);key=a*np.int64(len(ng))+b;order=np.argsort(key);key=key[order];a=a[order];b=b[order];ll=ll[order];starts=np.r_[0,np.flatnonzero(np.diff(key))+1];aa=a[starts];bb=b[starts];lm=np.minimum.reduceat(ll,starts);row=np.r_[aa,bb];col=np.r_[bb,aa];dat=np.r_[lm,lm];return coo_matrix((dat,(row,col)),shape=(len(ng),len(ng))).tocsr(),ng

def route_blocks(origins,services,network):
    lons,lats,nx,ny,ui,vi,lens,on,od,sn,sd,nstats=network;origins=origins.copy();origins['network_node']=on;origins['network_snap_m']=od;stops=pd.DataFrame({'stop_idx':np.arange(len(services),dtype=np.int32),'lon':[s.lon for s in services],'lat':[s.lat for s in services],'mode':[s.mode for s in services],'network_node':sn,'network_snap_m':sd});origins['network_connected']=origins.network_snap_m<=ORIGIN_SNAP_MAX;stops['network_matched']=stops.network_snap_m<=STOP_SNAP_MAX;base=['wd_departures','wd_am_departures','wd_midday_departures','wd_pm_departures','wd_evening_departures','sat_departures','wd_useful_hours_15','wd_useful_hours_30','wd_useful_hours_60','sat_useful_hours_15','sat_useful_hours_30','sat_useful_hours_60','wd_access_15','wd_access_30','wd_access_60','sat_access_15','sat_access_30','sat_access_60','wd_rail_access','wd_frequent_bus_access','wd_any_access','sat_rail_access','sat_frequent_bus_access','sat_any_access','reachable_stop_count','raw_reachable_stop_calls_proxy']
    for c in base:origins[c]=0.
    for c in base:origins['sens_'+c]=0.
    vals=[('Newark Penn','urban',40.7347,-74.1642),('Journal Square','urban',40.7330,-74.0630),('Hoboken Terminal','urban',40.7357,-74.0301),('Paterson Downtown','urban',40.9168,-74.1718),('Elizabeth Station','inner suburban',40.6678,-74.2150),('New Brunswick Station','small city',40.4964,-74.4463),('Trenton Transit Center','small city',40.2188,-74.7542),('Camden Walter Rand','urban',39.9431,-75.1181),('Atlantic City Terminal','shore city',39.3633,-74.4417),('Morristown Green','inner suburban',40.7970,-74.4815),('Somerville Station','suburban',40.5686,-74.6099),('Freehold Center','suburban',40.2601,-74.2738),('Lakewood Center','suburban',40.0979,-74.2176),('Toms River Center','shore suburban',39.9537,-74.1979),('Hackettstown Station','small city',40.8518,-74.8350),('Phillipsburg Center','small city',40.6937,-75.1902),('Vineland Center','small city',39.4864,-75.0257),('Cape May Center','shore',38.9351,-74.9060),('Newton Center','rural center',41.0582,-74.7527),('Salem Center','rural center',39.5718,-75.4671)];trans=Transformer.from_crs(4326,26918,always_xy=True);vx,vy=trans.transform([v[3] for v in vals],[v[2] for v in vals]);ox,oy=trans.transform(origins.lon.to_numpy(),origins.lat.to_numpy());otree=cKDTree(np.column_stack([ox,oy]));_,vo=otree.query(np.column_stack([vx,vy]),k=1);vbo=defaultdict(list)
    for j,oi in enumerate(vo):vbo[int(oi)].append(vals[j])
    del otree;tile_stats=[];features=[];local=np.full(len(lons),-1,dtype=np.int32);tile=0
    for x0 in np.arange(-75.65,-73.85,.30):
      for y0 in np.arange(38.82,41.50,.30):
        tile+=1;x1=min(x0+.30,-73.85);y1=min(y0+.30,41.50);oidx=np.flatnonzero((origins.lon>=x0)&(origins.lon<x1)&(origins.lat>=y0)&(origins.lat<y1)&origins.network_connected)
        if not len(oidx):continue
        sm=stops.network_matched&(stops.lon>=x0-.045)&(stops.lon<x1+.045)&(stops.lat>=y0-.045)&(stops.lat<y1+.045);sidx=np.flatnonzero(sm.to_numpy())
        if not len(sidx):tile_stats.append({'tile':tile,'origins':len(oidx),'stops':0,'nodes':0,'edges':0,'reach_pairs':0});continue
        nm=(lons>=x0-.045)&(lons<x1+.045)&(lats>=y0-.045)&(lats<y1+.045);graph,ng=build_tile_graph(nm,ui,vi,lens,local);ol=local[origins.loc[oidx,'network_node'].to_numpy(np.int32)];valid=ol>=0;oidx=oidx[valid];ol=ol[valid]
        if not len(oidx):local[ng]=-1;continue
        groups=defaultdict(list)
        for si in sidx:
            ln=local[int(stops.loc[si,'network_node'])]
            if ln>=0:groups[int(ln)].append(int(si))
        src=np.array(list(groups),dtype=np.int32);reach=[[] for _ in range(len(oidx))];pairs=0;osnap=origins.loc[oidx,'network_snap_m'].to_numpy()
        for b0 in range(0,len(src),8):
            ss=src[b0:b0+8];dist=dijkstra(graph,directed=False,indices=ss,limit=MAX_PATH,return_predecessors=False);dist=dist[None,:] if dist.ndim==1 else dist;sub=dist[:,ol]
            for r,ln in enumerate(ss):
                basev=sub[r];finite=np.isfinite(basev)
                if not finite.any():continue
                for si in groups[int(ln)]:
                    total=basev+osnap+float(stops.loc[si,'network_snap_m']);limit=SENS_BUS if services[si].mode=='bus' else SENS_RAIL;ok=np.flatnonzero(finite&(total<=limit));pairs+=len(ok)
                    for q in ok:reach[int(q)].append((si,float(total[q])))
            del dist,sub
        for pos,oi in enumerate(oidx):
            m=union_metrics(reach[pos],services,False);ms=union_metrics(reach[pos],services,True)
            for c,v in m.items():origins.at[oi,c]=v
            for c,v in ms.items():origins.at[oi,'sens_'+c]=v
            if int(oi) in vbo:
                ranked=sorted(reach[pos],key=lambda x:x[1])
                for val in vbo[int(oi)]:
                    props={'location':val[0],'type':val[1],'block_geoid':origins.at[oi,'GEOID20'],'tract_geoid':origins.at[oi,'tract_geoid'],'origin_snap_m':float(origins.at[oi,'network_snap_m']),'reachable_stops_sensitivity':len(ranked),'nearest_stop_uid':services[ranked[0][0]].uid if ranked else '', 'nearest_stop_operator':services[ranked[0][0]].operator if ranked else '', 'nearest_stop_mode':services[ranked[0][0]].mode if ranked else '', 'nearest_stop_network_m':ranked[0][1] if ranked else None,'weekday_departures':m['wd_departures'],'raw_stop_call_proxy':m['raw_reachable_stop_calls_proxy'],'dedup_removed':m['raw_reachable_stop_calls_proxy']-m['wd_departures']};features.append({'type':'Feature','properties':props,'geometry':{'type':'Point','coordinates':[float(origins.at[oi,'lon']),float(origins.at[oi,'lat'])]}})
        tile_stats.append({'tile':tile,'bbox':json.dumps([x0,y0,x1,y1]),'origins':len(oidx),'stops':len(sidx),'unique_stop_nodes':len(src),'nodes':len(ng),'edges':int(graph.nnz/2),'reach_pairs':pairs});local[ng]=-1;del graph,ng,nm,reach;gc.collect();log(f'tile {tile}: origins={len(oidx):,}, stops={len(sidx):,}, reach={pairs:,}')
    origins['network_status']=np.where(origins.network_connected,'connected','disconnected_origin');nstats.update({'origin_count':int(len(origins)),'connected_origin_count':int(origins.network_connected.sum()),'disconnected_origin_count':int((~origins.network_connected).sum()),'stop_count':int(len(stops)),'matched_stop_count':int(stops.network_matched.sum()),'unmatched_stop_count':int((~stops.network_matched).sum()),'origin_snap_max_m':ORIGIN_SNAP_MAX,'stop_snap_max_m':STOP_SNAP_MAX});return origins,stops,tile_stats,nstats,{'type':'FeatureCollection','features':features}

def aggregate_tracts(blocks):
    values=['wd_departures','wd_am_departures','wd_midday_departures','wd_pm_departures','wd_evening_departures','sat_departures','wd_useful_hours_15','wd_useful_hours_30','wd_useful_hours_60','sat_useful_hours_15','sat_useful_hours_30','sat_useful_hours_60'];flags=['wd_access_15','wd_access_30','wd_access_60','sat_access_15','sat_access_30','sat_access_60','wd_rail_access','wd_frequent_bus_access','wd_any_access','sat_rail_access','sat_frequent_bus_access','sat_any_access'];rows=[]
    for tract,g in blocks.groupby('tract_geoid',sort=False):
        pop=float(g.pop_scaled_2024.sum());jobs=float(g.jobs_2023_block.sum());r={'GEOID':tract,'block_count':len(g),'origin_population_2024':pop,'origin_jobs_2023':jobs,'disconnected_population_share':float((g.pop_scaled_2024*(~g.network_connected)).sum()/pop) if pop else np.nan,'disconnected_job_share':float((g.jobs_2023_block*(~g.network_connected)).sum()/jobs) if jobs else np.nan}
        for pre in ('','sens_'):
            for c in values:r[pre+'pop_weighted_'+c]=float((g.pop_scaled_2024*g[pre+c]).sum()/pop) if pop else np.nan;r[pre+'job_weighted_'+c]=float((g.jobs_2023_block*g[pre+c]).sum()/jobs) if jobs else np.nan
            for c in flags:r[pre+'population_share_'+c]=float((g.pop_scaled_2024*g[pre+c]).sum()/pop) if pop else np.nan;r[pre+'job_share_'+c]=float((g.jobs_2023_block*g[pre+c]).sum()/jobs) if jobs else np.nan
        rows.append(r)
    tr=pd.DataFrame(rows);x=np.log1p(tr.pop_weighted_wd_departures.fillna(0));tr['accessible_service_log1p']=x;tr['accessible_service_percentile']=x.rank(method='average',pct=True)*100;xs=np.log1p(tr.sens_pop_weighted_wd_departures.fillna(0));tr['sens_accessible_service_percentile']=xs.rank(method='average',pct=True)*100;return tr

def main():
    log('starting accessible-service analysis');origins,nj,recon,sources,paths=load_blocks_and_jobs();services,feeds,fs=prepare_gtfs(nj);sources.extend(fs);log(f'usable service stops: {len(services):,}');trans=Transformer.from_crs(4326,26918,always_xy=True);ox,oy=trans.transform(origins.lon.to_numpy(),origins.lat.to_numpy());sx,sy=trans.transform(np.array([s.lon for s in services]),np.array([s.lat for s in services]));network=prepare_network(paths['osm'],np.column_stack([ox,oy]),np.column_stack([sx,sy]));blocks,stops,tiles,nstats,vg=route_blocks(origins,services,network);tracts=aggregate_tracts(blocks);summary={'retrieved_at':RETRIEVED_AT,'representative_tuesday':TUESDAY.isoformat(),'representative_saturday':SATURDAY.isoformat(),'primary_thresholds_m':{'bus':PRIMARY_BUS,'rail_light_rail_rapid_transit_ferry':PRIMARY_RAIL},'sensitivity_thresholds_m':{'bus':SENS_BUS,'rail_light_rail_rapid_transit_ferry':SENS_RAIL},'frequency_coverage_convention':f'at least {SUSTAINED_HOURS} one-hour bins between 06:00 and 24:00 meet the threshold','population_reconciliation':recon,'network':nstats,'feed_count_audited':len(feeds),'feed_count_included':sum(bool(r['included']) for r in feeds),'service_stop_count':len(services),'tract_count':len(tracts),'origin_block_count':len(blocks),'reachable_population_share':float((blocks.pop_scaled_2024*blocks.wd_any_access).sum()/blocks.pop_scaled_2024.sum()),'rail_access_population_share':float((blocks.pop_scaled_2024*blocks.wd_rail_access).sum()/blocks.pop_scaled_2024.sum()),'frequent_bus_population_share':float((blocks.pop_scaled_2024*blocks.wd_frequent_bus_access).sum()/blocks.pop_scaled_2024.sum()),'median_pop_weighted_wd_departures':float(tracts.pop_weighted_wd_departures.median()),'validation_location_count':len(vg['features']),'dedup_invariant_violations':int((blocks.wd_departures>blocks.raw_reachable_stop_calls_proxy).sum()),'limitations':['Population and employment within each Census block are represented at the Census interior point before network snapping.','The pedestrian graph uses the current OpenStreetMap New Jersey extract; unmapped walkways and entrances are absent.','Frequency coverage is based on unique reachable departures aggregated across accessible fixed-route services, not a single-route scheduled headway.','Services without usable current public GTFS are identified in the feed inventory and excluded.']};blocks.to_csv(OUT/'block_accessibility.csv.gz',index=False,compression='gzip');tracts.to_csv(OUT/'tract_accessibility.csv',index=False);pd.DataFrame(feeds).to_csv(OUT/'gtfs_feed_inventory.csv',index=False);pd.DataFrame(OMISSIONS).to_csv(OUT/'material_omissions.csv',index=False);pd.DataFrame(sources).to_csv(OUT/'source_register.csv',index=False);pd.DataFrame(tiles).to_csv(OUT/'network_tile_qa.csv',index=False);stops.to_csv(OUT/'stop_network_matching.csv',index=False);(OUT/'validation_locations.geojson').write_text(json.dumps(vg));(OUT/'analysis_summary.json').write_text(json.dumps(summary,indent=2));(OUT/'network_summary.json').write_text(json.dumps(nstats,indent=2));qa=['NEW JERSEY TRANSIT ACCESSIBILITY — COMPUTATIONAL QA',f'Retrieved: {RETRIEVED_AT}',f'Representative Tuesday: {TUESDAY.isoformat()}',f'Representative Saturday: {SATURDAY.isoformat()}',f'Origin blocks: {len(blocks):,}',f'Tracts: {len(tracts):,}',f'Included feeds: {summary["feed_count_included"]}/{summary["feed_count_audited"]}',f'Service stops: {len(services):,}',f'Connected origins: {nstats["connected_origin_count"]:,}',f'Disconnected origins: {nstats["disconnected_origin_count"]:,}',f'Unmatched stops: {nstats["unmatched_stop_count"]:,}',f'2024 tract population control total: {recon["acs2024_total"]:,.3f}',f'Scaled block population total: {recon["scaled_block_population_total"]:,.3f}',f'Population reconciliation difference: {recon["scaled_block_population_total"]-recon["acs2024_total"]:,.9f}',f'LODES jobs input total: {recon["lodes_jobs_total"]:,.0f}',f'Origin jobs total: {recon["origin_jobs_total"]:,.0f}',f'Trip de-duplication invariant violations: {summary["dedup_invariant_violations"]}',f'Validation locations produced: {summary["validation_location_count"]}','','Material omissions are listed in material_omissions.csv.'];(OUT/'QA_REPORT.txt').write_text('\n'.join(qa));shutil.copy(__file__,OUT/'build_accessible_service.py');(OUT/'requirements-accessibility.txt').write_text('pandas==2.2.3\nnumpy==1.26.4\ngeopandas==1.0.1\npyogrio==0.10.0\nshapely==2.0.6\npyproj==3.7.0\nscipy==1.14.1\npyrosm==0.6.2\npyroaring==0.5.1\n');log('analysis complete');log(json.dumps(summary,indent=2))
if __name__=='__main__':main()
