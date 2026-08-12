#!/usr/bin/env python3
import csv, json, urllib.request, pathlib
url='https://data.transportation.gov/resource/2u7n-ub22.json?$limit=50000'
req=urllib.request.Request(url,headers={'User-Agent':'NJ-Transit-Score-Research/1.0'})
with urllib.request.urlopen(req,timeout=120) as r: rows=json.load(r)
selected=[]
for row in rows:
    name=(row.get('agency_name') or '').lower()
    uza=(row.get('uza_name') or '').lower()
    if row.get('state')=='NJ' or 'port authority trans-hudson' in name or 'patco' in name or ('new york--jersey city--newark' in uza and any(k in name for k in ['port authority trans-hudson','ny waterway'])):
        selected.append(row)
out={'retrieval_url':url,'count':len(rows),'keys':sorted({k for row in rows for k in row}),'selected':selected}
pathlib.Path('out').mkdir(exist_ok=True)
pathlib.Path('out/fta_gtfs_inventory_nj.json').write_text(json.dumps(out,indent=2))
fields=sorted({k for row in selected for k in row if k!='weblink'})+['weblink_url']
with open('out/fta_gtfs_inventory_nj.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
    for row in selected:
        rr={k:v for k,v in row.items() if k!='weblink'}; rr['weblink_url']=(row.get('weblink') or {}).get('url',''); w.writerow(rr)
print('rows',len(rows),'selected',len(selected),'agencies',len({r.get('ntd_id') for r in selected}))
