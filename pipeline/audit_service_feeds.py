#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, pathlib, urllib.request, zipfile
from datetime import date, datetime, timedelta, timezone

OUT = pathlib.Path('out_feed_audit'); OUT.mkdir(exist_ok=True)
WORK = pathlib.Path('work/feed_audit'); WORK.mkdir(parents=True, exist_ok=True)
UA = {'User-Agent':'NJ-Transit-Score-Service-Access/1.0 (+public research)'}
NJ_BBOX=(-75.60,38.82,-73.87,41.38)

FEEDS = [
 {'id':'njt_bus','operator':'NJ TRANSIT Bus','modes':'bus','urls':['https://www.njtransit.com/bus_data.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-new-jersey-transit-nj-transit-gtfs-508.zip?alt=media']},
 {'id':'njt_rail','operator':'NJ TRANSIT Rail and Light Rail','modes':'commuter rail; light rail','urls':['https://www.njtransit.com/rail_data.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-new-jersey-transit-nj-transit-gtfs-509.zip?alt=media']},
 {'id':'path','operator':'PATH','modes':'rapid transit','urls':['https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/14843/PATHGTFS.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-port-authority-trans-hudson-path-gtfs-517.zip?alt=media']},
 {'id':'patco','operator':'PATCO Speedline','modes':'rapid transit','urls':['https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/13562/PATCO_GTFS.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-patco-speedline-gtfs-3035.zip?alt=media']},
 {'id':'septa_rail','operator':'SEPTA Regional Rail','modes':'commuter rail','urls':['https://www3.septa.org/developer/google_rail.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-pennsylvania-southeastern-pennsylvania-transportation-authority-gtfs-503.zip?alt=media']},
 {'id':'septa_bus','operator':'SEPTA surface transit','modes':'bus; rapid transit; light rail','urls':['https://www3.septa.org/developer/google_bus.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-pennsylvania-southeastern-pennsylvania-transportation-authority-gtfs-502.zip?alt=media']},
 {'id':'amtrak','operator':'Amtrak','modes':'intercity rail','urls':['https://content.amtrak.com/content/gtfs/GTFS.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-unknown-amtrak-gtfs-11.zip?alt=media']},
 {'id':'academy','operator':'Academy Lines','modes':'commuter bus','urls':['https://www.njtransit.com/Academy_bus_data.zip']},
 {'id':'coachusa','operator':'Coach USA New Jersey affiliates','modes':'commuter bus','urls':['https://api.prod.coachusa.com/gtfs']},
 {'id':'lakeland','operator':'Lakeland Bus Lines','modes':'commuter bus','urls':['https://content.njtransit.com/sites/default/files/developers-resources/LakelandBusLines_bus_data.zip']},
 {'id':'boxcar','operator':'Boxcar','modes':'commuter bus','urls':['https://boxcar-gtfs.vercel.app/api/gtfs','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-boxcar-gtfs-3105.zip?alt=media']},
 {'id':'nywaterway','operator':'NY Waterway ferry','modes':'ferry','urls':['https://nywaterway.connexionz.net/rtt/public/resource/gtfs.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-york-ny-waterway-gtfs-3192.zip?alt=media']},
 {'id':'nywaterway_bus','operator':'NY Waterway shuttle buses','modes':'bus','urls':['https://services.saucontds.com/service-schedule-server/gtfsFeed/749f33f0-b1d7-4be2-b0ea-3f63cf39073e']},
 {'id':'seastreak','operator':'Seastreak','modes':'ferry','urls':['https://seastreak.com/api/transit/google_transit.zip']},
 {'id':'princeton','operator':'Princeton University TigerTransit','modes':'bus','urls':['https://princeton.tripshot.com/v1/gtfs.zip']},
 {'id':'rutgers','operator':'Rutgers University Transit','modes':'bus','urls':['https://rutgers.tripshot.com/v1/gtfs.zip','https://rutgers.tripshot.com/gtfs.zip','https://rutgers.tripshot.com/v1/gtfs','https://rutgers.tripshot.com/gtfs']},
 {'id':'gloucester','operator':'Gloucester County transit','modes':'bus','urls':['https://www.njtransit.com/Gloucester_Co_bus_data.zip']},
 {'id':'atlantic_county','operator':'Atlantic County transit','modes':'bus','urls':['https://www.njtransit.com/AtlanticCo_bus_data.zip']},
 {'id':'sjta','operator':'South Jersey Transportation Authority','modes':'bus','urls':['https://www.njtransit.com/SJTA_bus_data.zip']},
 {'id':'cumberland','operator':'Cumberland County transit','modes':'bus','urls':['https://www.njtransit.com/Cumberland_Co_bus_data.zip']},
 {'id':'burlington','operator':'Burlington County BurLINK','modes':'bus','urls':['https://www.njtransit.com/BurlingtonShuttles_bus_data.zip']},
 {'id':'somerset','operator':'Somerset County transit','modes':'bus','urls':['https://www.njtransit.com/SomersetCounty_bus_data.zip']},
 {'id':'hunterdon','operator':'Hunterdon County LINK','modes':'bus','urls':['https://www.njtransit.com/Hunterdon_Co_bus_data.zip']},
 {'id':'broadway','operator':'Broadway Bus Corporation','modes':'bus','urls':['https://www.njtransit.com/broadway_bus_data.zip']},
 {'id':'warren','operator':'Warren County transit','modes':'bus','urls':['https://www.njtransit.com/WCT_bus_data.zip']},
 {'id':'sussex','operator':'Sussex County transit','modes':'bus','urls':['https://www.njtransit.com/sussexcounty_bus_data.zip']},
]

def download(url, path):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=240) as r, open(path,'wb') as f:
        while True:
            b=r.read(1<<20)
            if not b: break
            f.write(b)

def read_csv(z,name):
    if name not in z.namelist(): return []
    return list(csv.DictReader(io.TextIOWrapper(z.open(name),encoding='utf-8-sig',errors='replace')))

def parse_date(s):
    try: return datetime.strptime(str(s),'%Y%m%d').date()
    except Exception: return None

def service_coverage(calendar, exceptions):
    starts=[]; ends=[]
    for r in calendar:
        a=parse_date(r.get('start_date')); b=parse_date(r.get('end_date'))
        if a: starts.append(a)
        if b: ends.append(b)
    for r in exceptions:
        d=parse_date(r.get('date'))
        if d: starts.append(d); ends.append(d)
    return (min(starts) if starts else None, max(ends) if ends else None)

def active_services(calendar, exceptions, d):
    dow=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'][d.weekday()]
    active=set()
    for r in calendar:
        a=parse_date(r.get('start_date')); b=parse_date(r.get('end_date'))
        if a and b and a<=d<=b and r.get(dow,'0')=='1': active.add(r.get('service_id',''))
    for r in exceptions:
        if parse_date(r.get('date'))==d:
            sid=r.get('service_id','')
            if r.get('exception_type')=='1': active.add(sid)
            elif r.get('exception_type')=='2': active.discard(sid)
    return active

def is_nj(lon,lat):
    return NJ_BBOX[0] <= lon <= NJ_BBOX[2] and NJ_BBOX[1] <= lat <= NJ_BBOX[3]

records=[]
for spec in FEEDS:
    rec={k:spec[k] for k in ('id','operator','modes')}
    rec.update({'retrieved_at':datetime.now(timezone.utc).isoformat(),'status':'failed','url_used':'','file_bytes':0,'sha256':'','service_start':'','service_end':'','route_types':'','stops_total':0,'stops_nj_bbox':0,'routes':0,'trips':0,'error':''})
    errors=[]
    path=WORK/f"{spec['id']}.zip"
    for url in spec['urls']:
        try:
            download(url,path)
            with zipfile.ZipFile(path) as z:
                names=set(z.namelist())
                required={'stops.txt','routes.txt','trips.txt','stop_times.txt'}
                if not required.issubset(names): raise ValueError('missing required GTFS files')
                stops=read_csv(z,'stops.txt'); routes=read_csv(z,'routes.txt'); trips=read_csv(z,'trips.txt')
                cal=read_csv(z,'calendar.txt'); ex=read_csv(z,'calendar_dates.txt')
                a,b=service_coverage(cal,ex)
                nj=0
                for s in stops:
                    try:
                        if is_nj(float(s.get('stop_lon','')),float(s.get('stop_lat',''))): nj+=1
                    except Exception: pass
                import hashlib
                rec.update({'status':'downloaded','url_used':url,'file_bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'service_start':a.isoformat() if a else '','service_end':b.isoformat() if b else '','route_types':';'.join(sorted({r.get('route_type','') for r in routes})),'stops_total':len(stops),'stops_nj_bbox':nj,'routes':len(routes),'trips':len(trips),'calendar':cal,'calendar_dates':ex})
            break
        except Exception as e:
            errors.append(f'{url}: {type(e).__name__}: {e}')
    if rec['status']!='downloaded': rec['error']=' | '.join(errors)
    records.append(rec)

usable=[r for r in records if r['status']=='downloaded' and r['stops_nj_bbox']>0]
starts=[date.fromisoformat(r['service_start']) for r in usable if r['service_start']]
ends=[date.fromisoformat(r['service_end']) for r in usable if r['service_end']]
common_start=max(starts) if starts else None; common_end=min(ends) if ends else None
# Select nearest dates within common calendar coverage. Exclude federal holidays by explicit 2026 list.
holidays={date(2026,1,1),date(2026,1,19),date(2026,2,16),date(2026,5,25),date(2026,6,19),date(2026,7,3),date(2026,9,7),date(2026,10,12),date(2026,11,11),date(2026,11,26),date(2026,12,25)}
today=datetime.now(timezone.utc).date()
def select_weekday(wd):
    if not common_start or not common_end or common_start>common_end: return None
    candidates=[common_start+timedelta(days=i) for i in range((common_end-common_start).days+1)]
    candidates=[d for d in candidates if d.weekday()==wd and d not in holidays]
    if not candidates: return None
    return min(candidates,key=lambda d:(abs((d-today).days), 0 if d<=today else 1))
tue=select_weekday(1); sat=select_weekday(5)

for r in records:
    cal=r.pop('calendar',[]); ex=r.pop('calendar_dates',[])
    if r['status']=='downloaded':
        r['tuesday_active_services']=len(active_services(cal,ex,tue)) if tue else ''
        r['saturday_active_services']=len(active_services(cal,ex,sat)) if sat else ''
        r['included_candidate']=bool(r['stops_nj_bbox']>0 and tue and sat and date.fromisoformat(r['service_start'])<=min(tue,sat) and date.fromisoformat(r['service_end'])>=max(tue,sat)) if r['service_start'] and r['service_end'] else False
    else:
        r['tuesday_active_services']=''; r['saturday_active_services']=''; r['included_candidate']=False

fields=['id','operator','modes','status','included_candidate','url_used','retrieved_at','file_bytes','sha256','service_start','service_end','tuesday_active_services','saturday_active_services','route_types','stops_total','stops_nj_bbox','routes','trips','error']
with open(OUT/'feed_audit.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(records)
summary={'retrieved_at':datetime.now(timezone.utc).isoformat(),'common_start':common_start.isoformat() if common_start else None,'common_end':common_end.isoformat() if common_end else None,'representative_tuesday':tue.isoformat() if tue else None,'representative_saturday':sat.isoformat() if sat else None,'downloaded':sum(r['status']=='downloaded' for r in records),'usable_nj_bbox':len(usable),'included_candidates':sum(bool(r['included_candidate']) for r in records),'records':records}
(OUT/'feed_audit.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='records'},indent=2))
