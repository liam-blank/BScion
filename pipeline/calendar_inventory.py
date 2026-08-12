#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, pathlib, urllib.request, zipfile, hashlib
from datetime import date, datetime, timedelta, timezone

OUT=pathlib.Path('out'); OUT.mkdir(exist_ok=True)
WORK=pathlib.Path('work/feeds'); WORK.mkdir(parents=True,exist_ok=True)
UA='NJ-Transit-Score-Accessible-Service/1.0 (public-interest research)'

FEEDS=[
 {'id':'njt_bus','operator':'NJ TRANSIT Bus','url':'https://www.njtransit.com/bus_data.zip','authority':'NJ TRANSIT','modes':'bus','consequential':True},
 {'id':'njt_rail','operator':'NJ TRANSIT Rail and Light Rail','url':'https://www.njtransit.com/rail_data.zip','authority':'NJ TRANSIT','modes':'commuter rail; light rail; hybrid rail','consequential':True},
 {'id':'path','operator':'PATH','url':'https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/14843/PATHGTFS.zip','authority':'FTA National RTAP / PATH','modes':'heavy rail','consequential':True},
 {'id':'patco','operator':'PATCO','url':'https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/13562/PATCO_GTFS.zip','authority':'FTA National RTAP / PATCO','modes':'heavy rail','consequential':True},
 {'id':'academy','operator':'Academy Lines','url':'https://www.njtransit.com/Academy_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'commuter bus','consequential':True},
 {'id':'coachusa','operator':'Coach USA New Jersey services','url':'https://api.prod.coachusa.com/gtfs','authority':'FTA GTFS inventory / Coach USA','modes':'commuter bus','consequential':True},
 {'id':'lakeland','operator':'Lakeland Bus Lines','url':'https://content.njtransit.com/sites/default/files/developers-resources/LakelandBusLines_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'commuter bus','consequential':True},
 {'id':'nywaterway_ferry','operator':'NY Waterway Ferry','url':'https://nywaterway.connexionz.net/rtt/public/resource/gtfs.zip','authority':'FTA GTFS inventory / NY Waterway','modes':'ferry','consequential':True},
 {'id':'nywaterway_bus','operator':'NY Waterway Shuttle Bus','url':'https://services.saucontds.com/service-schedule-server/gtfsFeed/749f33f0-b1d7-4be2-b0ea-3f63cf39073e','authority':'FTA GTFS inventory / NY Waterway','modes':'bus','consequential':True},
 {'id':'seastreak','operator':'Seastreak','url':'https://seastreak.com/api/transit/google_transit.zip','authority':'FTA GTFS inventory / Seastreak','modes':'ferry','consequential':True},
 {'id':'boxcar','operator':'Boxcar','url':'https://boxcar-gtfs.vercel.app/api/gtfs','authority':'Mobility Database / Boxcar','modes':'commuter bus','consequential':True},
 {'id':'amtrak','operator':'Amtrak','url':'https://content.amtrak.com/content/gtfs/GTFS.zip','authority':'Amtrak','modes':'intercity rail','consequential':True},
 {'id':'septa','operator':'SEPTA','url':'https://www3.septa.org/developer/gtfs_public.zip','authority':'SEPTA','modes':'regional rail; bus; metro','consequential':True},
 {'id':'mta_si_bus','operator':'MTA Staten Island Bus','url':'https://rrgtfsfeeds.s3.amazonaws.com/gtfs_si.zip','authority':'MTA','modes':'bus','consequential':True},
 {'id':'gloucester','operator':'Gloucester County','url':'https://www.njtransit.com/Gloucester_Co_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','consequential':False},
 {'id':'atlantic','operator':'Atlantic County','url':'https://www.njtransit.com/AtlanticCo_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','consequential':False},
 {'id':'sjta','operator':'South Jersey Transportation Authority','url':'https://www.njtransit.com/SJTA_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','consequential':False},
 {'id':'cumberland','operator':'Cumberland County','url':'https://www.njtransit.com/Cumberland_Co_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','consequential':False},
 {'id':'burlington','operator':'Burlington County Shuttles','url':'https://www.njtransit.com/BurlingtonShuttles_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','consequential':False},
 {'id':'somerset','operator':'Somerset County','url':'https://www.njtransit.com/SomersetCounty_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','consequential':False},
 {'id':'hunterdon','operator':'Hunterdon LINK','url':'https://www.njtransit.com/Hunterdon_Co_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','consequential':False},
 {'id':'broadway','operator':'Broadway Bus','url':'https://www.njtransit.com/broadway_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','consequential':False},
 {'id':'warren','operator':'Warren County','url':'https://www.njtransit.com/WCT_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','consequential':False},
 {'id':'sussex','operator':'Sussex County','url':'https://www.njtransit.com/sussexcounty_bus_data.zip','authority':'FTA GTFS inventory / NJ TRANSIT','modes':'bus','consequential':False},
]

def dl(url,path):
 req=urllib.request.Request(url,headers={'User-Agent':UA})
 with urllib.request.urlopen(req,timeout=180) as r, open(path,'wb') as f:
  while True:
   b=r.read(1<<20)
   if not b: break
   f.write(b)

def read_csv(z,name):
 with z.open(name) as f:
  return list(csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig',errors='replace')))

def normalize_zip(path,feed_id):
 z=zipfile.ZipFile(path)
 names=set(z.namelist())
 if {'stops.txt','routes.txt','trips.txt','stop_times.txt'}.issubset(names): return z,None
 nested=[n for n in names if n.lower().endswith('.zip')]
 # SEPTA public package includes separate transit and rail GTFS archives.
 if nested: return z,nested
 raise ValueError('required GTFS files not found')

def active_services(z,d):
 ds=d.strftime('%Y%m%d'); wd=d.strftime('%A').lower(); active=set()
 if 'calendar.txt' in z.namelist():
  for r in read_csv(z,'calendar.txt'):
   if r.get('start_date','')<=ds<=r.get('end_date','') and r.get(wd)=='1': active.add(r.get('service_id',''))
 if 'calendar_dates.txt' in z.namelist():
  for r in read_csv(z,'calendar_dates.txt'):
   if r.get('date')==ds:
    if r.get('exception_type')=='1': active.add(r.get('service_id',''))
    elif r.get('exception_type')=='2': active.discard(r.get('service_id',''))
 return active

def summarize_gtfs(z,prefix=''):
 names=set(z.namelist()); starts=[]; ends=[]
 if 'calendar.txt' in names:
  for r in read_csv(z,'calendar.txt'):
   starts.append(r.get('start_date','')); ends.append(r.get('end_date',''))
 if 'calendar_dates.txt' in names:
  for r in read_csv(z,'calendar_dates.txt'):
   starts.append(r.get('date','')); ends.append(r.get('date',''))
 starts=[x for x in starts if x]; ends=[x for x in ends if x]
 routes=read_csv(z,'routes.txt'); stops=read_csv(z,'stops.txt'); trips=read_csv(z,'trips.txt')
 njstops=0; bbox=[999,999,-999,-999]
 for r in stops:
  try: lat=float(r['stop_lat']); lon=float(r['stop_lon'])
  except: continue
  bbox=[min(bbox[0],lon),min(bbox[1],lat),max(bbox[2],lon),max(bbox[3],lat)]
  if 38.82<=lat<=41.50 and -75.65<=lon<=-73.85: njstops+=1
 return {'segment':prefix,'service_start':min(starts) if starts else '', 'service_end':max(ends) if ends else '',
         'route_types':','.join(sorted({r.get('route_type','') for r in routes})),
         'route_count':len(routes),'trip_count':len(trips),'stop_count':len(stops),'nj_stop_count':njstops,'bbox':bbox}

records=[]; usable=[]
for spec in FEEDS:
 rec=dict(spec); rec.update({'retrieved_at':datetime.now(timezone.utc).isoformat(),'download_ok':False,'error':'','bytes':0,'sha256':'','segments':[]})
 path=WORK/(spec['id']+'.zip')
 try:
  dl(spec['url'],path); rec['bytes']=path.stat().st_size; rec['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
  outer,nested=normalize_zip(path,spec['id'])
  if nested:
   for n in nested:
    blob=outer.read(n)
    try:
     inner=zipfile.ZipFile(io.BytesIO(blob)); s=summarize_gtfs(inner,n); rec['segments'].append(s)
    except Exception as e: rec['segments'].append({'segment':n,'error':str(e)})
  else: rec['segments'].append(summarize_gtfs(outer,''))
  rec['download_ok']=any('service_start' in s for s in rec['segments'])
  if rec['download_ok']: usable.append(spec['id'])
 except Exception as e: rec['error']=f'{type(e).__name__}: {e}'
 records.append(rec)

# Evaluate calendar overlap across successfully downloaded consequential feeds.
start=date(2026,8,13); end=date(2026,11,8); calendar=[]
for d in (start+timedelta(days=i) for i in range((end-start).days+1)):
 if d.weekday() not in (1,5): continue
 ok=[]
 for rec in records:
  if not rec['download_ok'] or not rec['consequential']: continue
  spans=[s for s in rec['segments'] if s.get('service_start') and s.get('service_end')]
  ds=d.strftime('%Y%m%d')
  if any(s['service_start']<=ds<=s['service_end'] for s in spans): ok.append(rec['id'])
 calendar.append({'date':d.isoformat(),'weekday':d.strftime('%A'),'consequential_feeds_in_span':len(ok),'feed_ids':'|'.join(ok)})

(OUT/'feed_calendar_inventory.json').write_text(json.dumps({'retrieved_at':datetime.now(timezone.utc).isoformat(),'feeds':records,'calendar_overlap':calendar},indent=2))
flat=[]
for r in records:
 if r['segments']:
  for s in r['segments']:
   flat.append({k:r.get(k,'') for k in ['id','operator','url','authority','modes','consequential','retrieved_at','download_ok','error','bytes','sha256']}|s)
 else: flat.append({k:r.get(k,'') for k in ['id','operator','url','authority','modes','consequential','retrieved_at','download_ok','error','bytes','sha256']})
fields=sorted({k for r in flat for k in r})
with open(OUT/'feed_calendar_inventory.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(flat)
with open(OUT/'calendar_overlap.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=['date','weekday','consequential_feeds_in_span','feed_ids']); w.writeheader(); w.writerows(calendar)
print('feeds',len(records),'downloaded',sum(r['download_ok'] for r in records))
