#!/usr/bin/env python3
from pathlib import Path

src_path = Path('pipeline/prepare_accessibility.py')
src = src_path.read_text()

# Frequency-expanded trips retain the route and direction metadata of their template trip.
src = src.replace(
    "calls=calls.merge(t[[c for c in ['trip_id','route_id','route_type','route_short_name','route_long_name'] if c in t.columns]],on='trip_id',how='left')",
    "calls['template_trip_id']=calls['trip_id'].astype(str).str.replace(r'~F\\d+$','',regex=True)\n"
    "     meta=t[[c for c in ['trip_id','route_id','route_type','route_short_name','route_long_name','direction_id','trip_headsign'] if c in t.columns]].rename(columns={'trip_id':'template_trip_id'})\n"
    "     calls=calls.merge(meta,on='template_trip_id',how='left')"
)

# TIGER/Line block geometry does not contain population. Retrieve 2020 PL 94-171
# block population from the Census API county by county and join by 15-digit GEOID.
old_block = """ pop='POP20' if 'POP20' in blocks.columns else 'POP'\n housing='HOUSING20' if 'HOUSING20' in blocks.columns else 'HOUSING'\n blocks=blocks[[geoid,aland,pop,housing,'geometry']].rename(columns={geoid:'block_geoid',aland:'aland_m2',pop:'pop20',housing:'housing20'})\n blocks['block_geoid']=blocks.block_geoid.astype(str); blocks['GEOID']=blocks.block_geoid.str[:11]\n blocks['pop20']=pd.to_numeric(blocks.pop20,errors='coerce').fillna(0); blocks['housing20']=pd.to_numeric(blocks.housing20,errors='coerce').fillna(0); blocks['aland_m2']=pd.to_numeric(blocks.aland_m2,errors='coerce').fillna(0)"""
new_block = """ blocks=blocks[[geoid,aland,'geometry']].rename(columns={geoid:'block_geoid',aland:'aland_m2'})\n blocks['block_geoid']=blocks.block_geoid.astype(str).str.zfill(15); blocks['GEOID']=blocks.block_geoid.str[:11]\n blocks['aland_m2']=pd.to_numeric(blocks.aland_m2,errors='coerce').fillna(0)\n pl_frames=[]\n for county_code in sorted(blocks.block_geoid.str[2:5].unique()):\n  params=[('get','P1_001N,H1_001N'),('for','block:*'),('in',f'state:34 county:{county_code} tract:*')]\n  pl_url='https://api.census.gov/data/2020/dec/pl?'+urllib.parse.urlencode(params)\n  pl_req=urllib.request.Request(pl_url,headers={'User-Agent':UA})\n  with urllib.request.urlopen(pl_req,timeout=180) as r: pl_rows=json.load(r)\n  pl=pd.DataFrame(pl_rows[1:],columns=pl_rows[0])\n  pl['block_geoid']=pl.state+pl.county+pl.tract+pl.block\n  pl['pop20']=pd.to_numeric(pl['P1_001N'],errors='coerce').fillna(0)\n  pl['housing20']=pd.to_numeric(pl['H1_001N'],errors='coerce').fillna(0)\n  pl_frames.append(pl[['block_geoid','pop20','housing20']])\n pl_all=pd.concat(pl_frames,ignore_index=True) if pl_frames else pd.DataFrame(columns=['block_geoid','pop20','housing20'])\n blocks=blocks.merge(pl_all,on='block_geoid',how='left')\n blocks['pop20']=blocks.pop20.fillna(0); blocks['housing20']=blocks.housing20.fillna(0)"""
if old_block not in src:
    raise RuntimeError('Expected TIGER population block was not found in prepare_accessibility.py')
src = src.replace(old_block, new_block)

# Preserve route names, route direction and headsign in schedule calls and trip summaries.
src = src.replace(
    "keep=['day','feed_id','feed_segment','operator','trip_uid','route_uid','route_type','mode_group','stop_uid','dep_seconds']",
    "keep=['day','feed_id','feed_segment','operator','trip_uid','route_uid','route_type','mode_group','stop_uid','dep_seconds']+[c for c in ['route_short_name','route_long_name','direction_id','trip_headsign'] if c in calls.columns]"
)
src = src.replace(
    "tsum=calls[['day','feed_id','feed_segment','operator','trip_uid','route_uid','route_type','mode_group']].drop_duplicates()",
    "tsum=calls[['day','feed_id','feed_segment','operator','trip_uid','route_uid','route_type','mode_group']+[c for c in ['route_short_name','route_long_name','direction_id','trip_headsign'] if c in calls.columns]].drop_duplicates()"
)

# Scale block population to each ACS tract total. In the rare tract with no 2020
# block population, allocate by 2020 housing units and then by land area.
old_scale = """ blocks['pop_scale']=np.where(blocks.tract_pop20>0,blocks.pop_2024/blocks.tract_pop20,np.nan)\n blocks['pop_2024_scaled']=blocks.pop20*blocks.pop_scale"""
new_scale = """ blocks['pop_scale']=np.where(blocks.tract_pop20>0,blocks.pop_2024/blocks.tract_pop20,np.nan)\n blocks['pop_2024_scaled']=blocks.pop20*blocks.pop_scale\n blocks['pop_allocation_method']=np.where(blocks.tract_pop20>0,'2020 block population scaled to ACS tract total','unallocated')\n zero_tract=(blocks.tract_pop20<=0)&(blocks.pop_2024.fillna(0)>0)\n housing_sum=blocks.groupby('GEOID').housing20.transform('sum')\n area_sum=blocks.groupby('GEOID').aland_m2.transform('sum')\n housing_weight=np.where(housing_sum>0,blocks.housing20/housing_sum,0.0)\n area_weight=np.where(area_sum>0,blocks.aland_m2/area_sum,0.0)\n blocks.loc[zero_tract,'pop_2024_scaled']=blocks.loc[zero_tract,'pop_2024']*np.where(housing_sum[zero_tract]>0,housing_weight[zero_tract],area_weight[zero_tract])\n blocks.loc[zero_tract,'pop_allocation_method']=np.where(housing_sum[zero_tract]>0,'housing-unit allocation for zero-population tract','land-area allocation for zero-population tract')"""
if old_scale not in src:
    raise RuntimeError('Expected block population scaling block was not found')
src = src.replace(old_scale, new_scale)

# The graph-node search tests the original block polygon, while the representative
# point remains the disclosed block origin.
src = src.replace("choose_nodes(oxy,origins.geometry.tolist(),tree,node_xy)", "choose_nodes(oxy,origins['geometry'].tolist(),tree,node_xy)")

# Avoid unnecessary large polygon exports; final source provenance points to the
# authoritative TIGER archive. Compact origin attributes are retained in Parquet.
old_return = """ blocks.to_file(PREP/'blocks_inputs.gpkg',layer='blocks',driver='GPKG')\n origins.drop(columns=['geometry'],errors='ignore').to_file(PREP/'origins.gpkg',layer='origins',driver='GPKG')\n return blocks,origins,acs"""
new_return = """ recon=blocks.groupby('GEOID',as_index=False).agg(block_count=('block_geoid','size'),pop20=('pop20','sum'),pop_2024_scaled=('pop_2024_scaled','sum'),jobs_2023_blocks=('jobs_2023_block','sum'),tract_pop20=('tract_pop20','first'),acs_pop_2024=('pop_2024','first'))\n recon['population_difference']=recon.pop_2024_scaled-recon.acs_pop_2024\n recon.to_csv(OUT/'block_tract_reconciliation.csv',index=False)\n block_meta={'all_blocks':int(len(blocks)),'resident_or_job_origins':int(len(origins)),'blocks_with_population':int((blocks.pop_2024_scaled.fillna(0)>0).sum()),'blocks_with_jobs':int((blocks.jobs_2023_block>0).sum()),'zero_population_control_tracts':int((recon.tract_pop20<=0).sum()),'scaled_population_total':float(blocks.pop_2024_scaled.sum()),'acs_population_total':float(acs.pop_2024.sum()),'population_reconciliation_max_abs':float(recon.population_difference.abs().max()),'lodes_jobs_total':float(blocks.jobs_2023_block.sum())}\n (OUT/'block_population_job_metadata.json').write_text(json.dumps(block_meta,indent=2))\n return blocks,origins,acs"""
if old_return not in src:
    raise RuntimeError('Expected block-output return block was not found in prepare_accessibility.py')
src = src.replace(old_return, new_return)

# GeoDataFrame geometry objects are not written into attribute Parquet files.
src = src.replace(
    "pq.write_table(pa.Table.from_pandas(origins,preserve_index=False),PREP/'origins_all.parquet',compression='zstd')",
    "origins_export=pd.DataFrame(origins.drop(columns=['geometry','origin_geometry'],errors='ignore'))\n pq.write_table(pa.Table.from_pandas(origins_export,preserve_index=False),PREP/'origins_all.parquet',compression='zstd')"
)
src = src.replace(
    "pq.write_table(pa.Table.from_pandas(origins_connected,preserve_index=False),PREP/'origins_connected.parquet',compression='zstd')",
    "origins_connected_export=pd.DataFrame(origins_connected.drop(columns=['geometry','origin_geometry'],errors='ignore'))\n pq.write_table(pa.Table.from_pandas(origins_connected_export,preserve_index=False),PREP/'origins_connected.parquet',compression='zstd')"
)

# A physical graph node can host stops from more than one mode; retain the mode-specific snap.
src = src.replace(
    "calls2=calls.merge(st[['stop_uid','source_idx','stop_snap_m','matched']],on='stop_uid',how='left')",
    "calls2=calls.merge(st[['stop_uid','mode_group','source_idx','stop_snap_m','matched']],on=['stop_uid','mode_group'],how='left')"
)

patched = Path('work/prepare_accessibility_effective.py')
patched.parent.mkdir(parents=True, exist_ok=True)
patched.write_text(src)
Path('out/reproducibility').mkdir(parents=True, exist_ok=True)
Path('out/reproducibility/prepare_accessibility.py').write_text(src)
exec(compile(src, str(patched), 'exec'), {'__name__': '__main__', '__file__': str(patched)})
