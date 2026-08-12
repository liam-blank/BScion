#!/usr/bin/env python3
import json, urllib.request, pathlib
url='https://data.transportation.gov/resource/2u7n-ub22.json?$limit=50000'
req=urllib.request.Request(url,headers={'User-Agent':'NJ-Transit-Score-Research/1.0'})
with urllib.request.urlopen(req,timeout=120) as r: rows=json.load(r)
out={'count':len(rows),'keys':sorted({k for row in rows for k in row}),'sample':rows[:3]}
needle=['new jersey','nj transit','patco','path','academy','coach usa','seastreak','princeton','rutgers','new jersey transit','port authority trans-hudson']
sel=[row for row in rows if any(n in json.dumps(row).lower() for n in needle)]
out['selected']=sel
pathlib.Path('out').mkdir(exist_ok=True)
pathlib.Path('out/fta_gtfs_inspection.json').write_text(json.dumps(out,indent=2))
print('rows',len(rows),'selected',len(sel),'keys',out['keys'])
