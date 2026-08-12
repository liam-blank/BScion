#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

# Use the public Census Reporter mirror of the current ACS release. The Census
# API endpoint currently returns a Missing Key response without credentials.
prepare_path = Path('pipeline/prepare_accessibility.py')
prepare = prepare_path.read_text()
acs_start = prepare.index(' # ACS tract inputs')
acs_end = prepare.index(' # Blocks', acs_start)
acs_replacement = ''' # ACS tract inputs from Census Reporter, which mirrors the current 2024 ACS five-year release.
 acs_url='https://api.censusreporter.org/1.0/data/show/latest?table_ids=B01003,B11001&geo_ids=140%7C04000US34'
 acs_req=urllib.request.Request(acs_url,headers={'User-Agent':UA})
 with urllib.request.urlopen(acs_req,timeout=240) as r: acs_payload=json.load(r)
 geography=acs_payload.get('geography',{})
 acs_rows=[]
 for full_geoid,tables in acs_payload.get('data',{}).items():
  if not full_geoid.startswith('14000US'): continue
  geoid=full_geoid.replace('14000US','',1)
  acs_rows.append({'GEOID':geoid,'NAME':geography.get(full_geoid,{}).get('name',full_geoid),'pop_2024':tables.get('B01003',{}).get('estimate',{}).get('B01003001'),'households_2024':tables.get('B11001',{}).get('estimate',{}).get('B11001001')})
 acs=pd.DataFrame(acs_rows)
 if len(acs)<2000: raise RuntimeError(f'Census Reporter returned only {len(acs)} New Jersey tracts')
 for c in ['pop_2024','households_2024']: acs[c]=pd.to_numeric(acs[c],errors='coerce')
 acs.to_csv(PREP/'acs_2024_tracts.csv',index=False)
'''
prepare_path.write_text(prepare[:acs_start] + acs_replacement + prepare[acs_end:])

# Harmonize the preparation wrapper with the Census Reporter input and retain
# the population and housing fields already present in the 2020 TIGER block file.
wrapper_path = Path('pipeline/run_prepare_accessibility.py')
wrapper = wrapper_path.read_text()
old_acs_guard = """if old_acs not in src:
    raise RuntimeError('Expected ACS query block was not found in prepare_accessibility.py')
src = src.replace(old_acs, new_acs)"""
new_acs_guard = """if old_acs in src:
    src = src.replace(old_acs, new_acs)
elif 'api.censusreporter.org' in src or 'acs_frames=[]' in src or 'acs_frames = []' in src:
    pass
else:
    raise RuntimeError('Expected ACS query block was not found in prepare_accessibility.py')"""
if old_acs_guard not in wrapper:
    raise RuntimeError('ACS compatibility patch point not found in run_prepare_accessibility.py')
wrapper = wrapper.replace(old_acs_guard, new_acs_guard)

old_block_guard = """if old_block not in src:
    raise RuntimeError('Expected TIGER population block was not found in prepare_accessibility.py')
src = src.replace(old_block, new_block)"""
new_block_guard = """if old_block not in src:
    raise RuntimeError('Expected TIGER population block was not found in prepare_accessibility.py')
# The official 2020 TIGER/Line New Jersey tabulation-block file contains POP20
# and HOUSING20. Retain those authoritative attributes rather than querying a
# credentialed API for the same values."""
if old_block_guard not in wrapper:
    raise RuntimeError('TIGER block compatibility patch point not found in run_prepare_accessibility.py')
wrapper = wrapper.replace(old_block_guard, new_block_guard)

old_return_prefix = "new_return = \"\"\" recon=blocks.groupby('GEOID',as_index=False)"
new_return_prefix = "new_return = \"\"\" blocks.to_parquet(PREP/'blocks_inputs.parquet',index=False,compression='zstd')\\n recon=blocks.groupby('GEOID',as_index=False)"
if old_return_prefix not in wrapper:
    raise RuntimeError('Block GeoParquet patch point not found in run_prepare_accessibility.py')
wrapper = wrapper.replace(old_return_prefix, new_return_prefix)
wrapper_path.write_text(wrapper)

aggregate_path = Path('pipeline/aggregate_accessibility.py')
aggregate = aggregate_path.read_text()
old_blocks = "blocks=gpd.read_file(PREP/'blocks_inputs.gpkg',layer='blocks')"
new_blocks = "blocks=gpd.read_parquet(PREP/'blocks_inputs.parquet')"
if old_blocks not in aggregate:
    raise RuntimeError('Block input patch point not found in aggregate_accessibility.py')
aggregate_path.write_text(aggregate.replace(old_blocks, new_blocks))

subprocess.run([sys.executable, 'pipeline/run_prepare_accessibility.py'], check=True)
subprocess.run([sys.executable, 'pipeline/run_aggregate_accessibility.py'], check=True)
