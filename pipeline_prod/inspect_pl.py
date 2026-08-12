#!/usr/bin/env python3
import json, pathlib, urllib.request, zipfile
url='https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/New_Jersey/nj2020.pl.zip'
out=pathlib.Path('pl_inspect_out'); out.mkdir(exist_ok=True)
p=out/'nj2020.pl.zip'
req=urllib.request.Request(url,headers={'User-Agent':'NJ-Transit-Score-Research/1.0'})
with urllib.request.urlopen(req,timeout=300) as r, open(p,'wb') as f:
    while True:
        b=r.read(1<<20)
        if not b: break
        f.write(b)
with zipfile.ZipFile(p) as z:
    names=z.namelist()
    result={'names':names,'size':p.stat().st_size,'files':{}}
    for name in names:
        if name.lower().endswith('.pl'):
            with z.open(name) as fh:
                lines=[]
                for _ in range(3):
                    raw=fh.readline()
                    if not raw: break
                    s=raw.decode('latin-1').rstrip('\r\n')
                    fields=s.split('|')
                    lines.append({'length':len(s),'field_count':len(fields),'fields':fields[:20],'tail':fields[-10:]})
                result['files'][name]=lines
    (out/'inspect.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
