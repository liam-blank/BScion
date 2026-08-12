#!/usr/bin/env python3
from pathlib import Path
import subprocess, sys
p=Path('pipeline/prepare_accessibility.py')
s=p.read_text()
old=""" params={'get':'NAME,B01003_001E,B11001_001E,B08201_002E,B08201_003E,B08301_001E,B08301_010E','for':'tract:*','in':'state:34 county:*'}
 url='https://api.census.gov/data/2024/acs/acs5?'+urllib.parse.urlencode(params)
 req=urllib.request.Request(url,headers={'User-Agent':UA})
 with urllib.request.urlopen(req,timeout=180) as r: rows=json.load(r)
 acs=pd.DataFrame(rows[1:],columns=rows[0])"""
new=""" acs_frames=[]
 for county_code in [f'{i:03d}' for i in range(1,42,2)]:
  params=[('get','NAME,B01003_001E,B11001_001E,B08201_002E,B08201_003E,B08301_001E,B08301_010E'),('for','tract:*'),('in','state:34'),('in',f'county:{county_code}')]
  url='https://api.census.gov/data/2024/acs/acs5?'+urllib.parse.urlencode(params)
  req=urllib.request.Request(url,headers={'User-Agent':UA})
  with urllib.request.urlopen(req,timeout=180) as r:
   payload=r.read().decode('utf-8',errors='replace')
  try: rows=json.loads(payload)
  except Exception as e: raise RuntimeError(f'ACS API failed for county {county_code}: {payload[:500]}') from e
  acs_frames.append(pd.DataFrame(rows[1:],columns=rows[0]))
 acs=pd.concat(acs_frames,ignore_index=True)"""
if old not in s: raise RuntimeError('ACS source block not found')
p.write_text(s.replace(old,new))
subprocess.run([sys.executable,'pipeline/run_prepare_accessibility.py'],check=True)
