#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

# The preparation wrappers were developed in successive stages. Harmonize their
# runtime patches without rewriting the underlying source files in the repository.
wrapper_path = Path('pipeline/run_prepare_accessibility.py')
wrapper = wrapper_path.read_text()
old_guard = """if old_acs not in src:
    raise RuntimeError('Expected ACS query block was not found in prepare_accessibility.py')
src = src.replace(old_acs, new_acs)"""
new_guard = """if old_acs in src:
    src = src.replace(old_acs, new_acs)
elif 'acs_frames=[]' in src or 'acs_frames = []' in src:
    pass
else:
    raise RuntimeError('Expected ACS query block was not found in prepare_accessibility.py')"""
if old_guard not in wrapper:
    raise RuntimeError('ACS compatibility patch point not found in run_prepare_accessibility.py')
wrapper = wrapper.replace(old_guard, new_guard)

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

subprocess.run([sys.executable, 'pipeline/run_prepare_accessibility_v3.py'], check=True)
subprocess.run([sys.executable, 'pipeline/run_aggregate_accessibility.py'], check=True)
