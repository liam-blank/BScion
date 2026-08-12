#!/usr/bin/env python3
from pathlib import Path
import subprocess, sys
p=Path('pipeline/prepare_accessibility.py')
s=p.read_text()
old="params={'get':'NAME,B01003_001E,B11001_001E,B08201_002E,B08201_003E,B08301_001E,B08301_010E','for':'tract:*','in':'state:34 county:*'}\n url='https://api.census.gov/data/2024/acs/acs5?'+urllib.parse.urlencode(params)"
new="params=[('get','NAME,B01003_001E,B11001_001E,B08201_002E,B08201_003E,B08301_001E,B08301_010E'),('for','tract:*'),('in','state:34'),('in','county:*')]\n url='https://api.census.gov/data/2024/acs/acs5?'+urllib.parse.urlencode(params)"
if old not in s: raise RuntimeError('ACS query block not found')
p.write_text(s.replace(old,new))
subprocess.run([sys.executable,'pipeline/run_prepare_accessibility.py'],check=True)
