#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

# Use the official 2024 ACS table-based summary files. They are public,
# credential-free, and contain the tract estimate columns required here.
prepare_path = Path('pipeline/prepare_accessibility.py')
prepare = prepare_path.read_text()
acs_start = prepare.index(' # ACS tract inputs')
acs_end = prepare.index(' # Blocks', acs_start)
acs_replacement = ''' # ACS tract inputs from official 2024 table-based summary files.
 acs_base='https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData'
 pop_path=DATA/'acsdt5y2024-b01003.dat'; hh_path=DATA/'acsdt5y2024-b11001.dat'
 download(acs_base+'/acsdt5y2024-b01003.dat',pop_path,600)
 download(acs_base+'/acsdt5y2024-b11001.dat',hh_path,600)
 pop_table=pd.read_csv(pop_path,sep='|',dtype={'GEO_ID':str},usecols=['GEO_ID','B01003_E001'],low_memory=False)
 hh_table=pd.read_csv(hh_path,sep='|',dtype={'GEO_ID':str},usecols=['GEO_ID','B11001_E001'],low_memory=False)
 pop_table=pop_table[pop_table.GEO_ID.str.startswith('1400000US34',na=False)].copy()
 hh_table=hh_table[hh_table.GEO_ID.str.startswith('1400000US34',na=False)].copy()
 pop_table['GEOID']=pop_table.GEO_ID.str[-11:]
 hh_table['GEOID']=hh_table.GEO_ID.str[-11:]
 acs=pop_table[['GEOID','B01003_E001']].merge(hh_table[['GEOID','B11001_E001']],on='GEOID',how='inner').rename(columns={'B01003_E001':'pop_2024','B11001_E001':'households_2024'})
 acs['NAME']=acs.GEOID
 for c in ['pop_2024','households_2024']: acs[c]=pd.to_numeric(acs[c],errors='coerce')
 if len(acs)<2000: raise RuntimeError(f'Official ACS summary files returned only {len(acs)} New Jersey tracts')
 acs.to_csv(PREP/'acs_2024_tracts.csv',index=False)
'''
prepare_path.write_text(prepare[:acs_start] + acs_replacement + prepare[acs_end:])

# Harmonize the preparation wrapper with the official ACS input and retain the
# population and housing fields already present in the 2020 TIGER block file.
wrapper_path = Path('pipeline/run_prepare_accessibility.py')
wrapper = wrapper_path.read_text()
old_acs_guard = """if old_acs not in src:
    raise RuntimeError('Expected ACS query block was not found in prepare_accessibility.py')
src = src.replace(old_acs, new_acs)"""
new_acs_guard = """if old_acs in src:
    src = src.replace(old_acs, new_acs)
elif 'acsdt5y2024-b01003.dat' in src or 'api.censusreporter.org' in src or 'acs_frames=[]' in src or 'acs_frames = []' in src:
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
