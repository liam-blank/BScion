#!/usr/bin/env python3
from pathlib import Path
src_path=Path('pipeline/prepare_accessibility.py')
src=src_path.read_text()
src=src.replace("calls=calls.merge(t[[c for c in ['trip_id','route_id','route_type','route_short_name','route_long_name'] if c in t.columns]],on='trip_id',how='left')", "calls['template_trip_id']=calls['trip_id'].astype(str).str.replace(r'~F\\d+$','',regex=True)\n     meta=t[[c for c in ['trip_id','route_id','route_type','route_short_name','route_long_name'] if c in t.columns]].rename(columns={'trip_id':'template_trip_id'})\n     calls=calls.merge(meta,on='template_trip_id',how='left')")
src=src.replace("choose_nodes(oxy,origins.geometry.tolist(),tree,node_xy)", "choose_nodes(oxy,origins['geometry'].tolist(),tree,node_xy)")
src=src.replace("pq.write_table(pa.Table.from_pandas(origins,preserve_index=False),PREP/'origins_all.parquet',compression='zstd')", "origins_export=pd.DataFrame(origins.drop(columns=['geometry','origin_geometry'],errors='ignore'))\n pq.write_table(pa.Table.from_pandas(origins_export,preserve_index=False),PREP/'origins_all.parquet',compression='zstd')")
src=src.replace("pq.write_table(pa.Table.from_pandas(origins_connected,preserve_index=False),PREP/'origins_connected.parquet',compression='zstd')", "origins_connected_export=pd.DataFrame(origins_connected.drop(columns=['geometry','origin_geometry'],errors='ignore'))\n pq.write_table(pa.Table.from_pandas(origins_connected_export,preserve_index=False),PREP/'origins_connected.parquet',compression='zstd')")
src=src.replace("calls2=calls.merge(st[['stop_uid','source_idx','stop_snap_m','matched']],on='stop_uid',how='left')", "calls2=calls.merge(st[['stop_uid','mode_group','source_idx','stop_snap_m','matched']],on=['stop_uid','mode_group'],how='left')")
patched=Path('work/prepare_accessibility_effective.py'); patched.parent.mkdir(parents=True,exist_ok=True); patched.write_text(src)
Path('out/reproducibility').mkdir(parents=True,exist_ok=True)
Path('out/reproducibility/prepare_accessibility.py').write_text(src)
exec(compile(src,str(patched),'exec'),{'__name__':'__main__','__file__':str(patched)})
