#!/usr/bin/env python3
from pathlib import Path
import subprocess, sys

wrapper = Path('pipeline/run_prepare_accessibility.py').read_text()
start = wrapper.index('# Census APIs require separate state and county geography clauses.')
end = wrapper.index('# TIGER/Line block geometry does not contain population.')
replacement = '''# Census APIs require county-by-county tract queries; the statewide wildcard form is not accepted reliably.
old_acs = """ params={'get':'NAME,B01003_001E,B11001_001E,B08201_002E,B08201_003E,B08301_001E,B08301_010E','for':'tract:*','in':'state:34 county:*'}
 url='https://api.census.gov/data/2024/acs/acs5?'+urllib.parse.urlencode(params)
 req=urllib.request.Request(url,headers={'User-Agent':UA})
 with urllib.request.urlopen(req,timeout=180) as r: rows=json.load(r)
 acs=pd.DataFrame(rows[1:],columns=rows[0])"""
new_acs = """ acs_frames=[]
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
if old_acs not in src:
    raise RuntimeError('Expected ACS source block was not found in prepare_accessibility.py')
src = src.replace(old_acs, new_acs)

'''
effective = wrapper[:start] + replacement + wrapper[end:]
out = Path('work/run_prepare_accessibility_v4_effective.py')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(effective)
subprocess.run([sys.executable, str(out)], check=True)
