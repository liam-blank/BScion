#!/usr/bin/env python3
import csv, io, json, os, pathlib, sys, urllib.request, zipfile
from datetime import datetime, timezone

ROOT=pathlib.Path('work')
ROOT.mkdir(exist_ok=True)
CATALOG=ROOT/'mobility-database-catalogs'
OUT=pathlib.Path('out')
OUT.mkdir(exist_ok=True)

# New Jersey and immediate cross-border service area.
NJ_BBOX=(-75.65,38.82,-73.85,41.50) # minlon,minlat,maxlon,maxlat

def intersects(bb):
    if not bb: return False
    try:
        minlat=float(bb['minimum_latitude']); maxlat=float(bb['maximum_latitude'])
        minlon=float(bb['minimum_longitude']); maxlon=float(bb['maximum_longitude'])
    except Exception: return False
    return not (maxlon < NJ_BBOX[0] or minlon > NJ_BBOX[2] or maxlat < NJ_BBOX[1] or minlat > NJ_BBOX[3])

def date_range(z):
    names=set(z.namelist())
    starts=[]; ends=[]
    if 'calendar.txt' in names:
        with z.open('calendar.txt') as f:
            rows=csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))
            for r in rows:
                if r.get('start_date'): starts.append(r['start_date'])
                if r.get('end_date'): ends.append(r['end_date'])
    if 'calendar_dates.txt' in names:
        with z.open('calendar_dates.txt') as f:
            rows=csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))
            ds=[r.get('date','') for r in rows if r.get('date')]
            starts += ds; ends += ds
    return (min(starts) if starts else '', max(ends) if ends else '')

def route_types(z):
    if 'routes.txt' not in z.namelist(): return ''
    with z.open('routes.txt') as f:
        vals=sorted({r.get('route_type','') for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))})
    return ','.join(vals)

def stop_extent(z):
    if 'stops.txt' not in z.namelist(): return None,0
    xs=[]; ys=[]; n=0
    with z.open('stops.txt') as f:
        for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig')):
            try: x=float(r['stop_lon']); y=float(r['stop_lat'])
            except Exception: continue
            xs.append(x); ys.append(y); n+=1
    return ((min(xs),min(ys),max(xs),max(ys)) if xs else None,n)

def download(url,path):
    req=urllib.request.Request(url,headers={'User-Agent':'NJ-Transit-Score-Research/1.0'})
    with urllib.request.urlopen(req,timeout=120) as r, open(path,'wb') as f:
        while True:
            b=r.read(1024*1024)
            if not b: break
            f.write(b)

rows=[]
for p in CATALOG.glob('catalogs/sources/gtfs/schedule/*.json'):
    try: d=json.loads(p.read_text())
    except Exception: continue
    loc=d.get('location') or {}; bb=loc.get('bounding_box') or {}
    if loc.get('subdivision_name')=='New Jersey' or intersects(bb):
        urls=d.get('urls') or {}
        rows.append({
            'mdb_source_id':d.get('mdb_source_id'), 'provider':d.get('provider',''), 'name':d.get('name',''),
            'status':d.get('status','active'), 'is_official':d.get('is_official',''),
            'subdivision':loc.get('subdivision_name',''), 'direct_url':urls.get('direct_download',''),
            'latest_url':urls.get('latest',''), 'license_url':urls.get('license',''),
            'catalog_path':str(p), 'bbox':json.dumps(bb,sort_keys=True),
        })
rows=sorted(rows,key=lambda r:(r['provider'],str(r['mdb_source_id'])))

for i,r in enumerate(rows):
    url=r['latest_url'] or r['direct_url']
    r.update({'download_ok':False,'download_error':'','file_bytes':0,'service_start':'','service_end':'','route_types':'','stop_count':0,'stop_extent':''})
    if not url or r['status'] not in ('active',''):
        continue
    path=ROOT/f"feed_{r['mdb_source_id']}.zip"
    try:
        download(url,path)
        r['file_bytes']=path.stat().st_size
        with zipfile.ZipFile(path) as z:
            required={'stops.txt','routes.txt','trips.txt','stop_times.txt'}
            if not required.issubset(set(z.namelist())): raise ValueError('missing required GTFS files')
            r['service_start'],r['service_end']=date_range(z)
            r['route_types']=route_types(z)
            ext,n=stop_extent(z); r['stop_count']=n; r['stop_extent']=json.dumps(ext)
        r['download_ok']=True
    except Exception as e:
        r['download_error']=f'{type(e).__name__}: {e}'

fields=list(rows[0].keys()) if rows else []
with open(OUT/'candidate_feeds.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
(OUT/'candidate_feeds.json').write_text(json.dumps({'retrieved_at':datetime.now(timezone.utc).isoformat(),'feeds':rows},indent=2))
print(f'wrote {len(rows)} candidates; {sum(bool(r["download_ok"]) for r in rows)} downloaded')
