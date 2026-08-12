#!/usr/bin/env python3
from pathlib import Path
src=Path('pipeline/aggregate_accessibility.py').read_text()
# Include disconnected resident/job origins as zero-service observations in statewide and tract denominators.
old=""" df=con.execute(\"\"\"\n SELECT o.*,d.day,\n        coalesce(b.departures,0) AS departures,"""
# The SQL block itself remains unchanged; append disconnected records after its .df() terminator.
needle=""" LEFT JOIN useful u ON o.reach_block_idx=u.reach_block_idx AND d.day=u.day\n \"\"\").df()\n df['access_15']="""
replacement=""" LEFT JOIN useful u ON o.reach_block_idx=u.reach_block_idx AND d.day=u.day\n \"\"\").df()\n all_o=pd.read_parquet(PREP/'origins_all.parquet')\n disconnected=all_o[~all_o.connected.fillna(False)].copy()\n if not disconnected.empty:\n  disconnected=pd.concat([disconnected.assign(day='weekday'),disconnected.assign(day='saturday')],ignore_index=True)\n  disconnected['reach_block_idx']=-1\n  for c in ['departures','departures_am_peak','departures_midday','departures_pm_peak','departures_evening','bus_departures','rail_departures','ferry_departures','raw_reachable_calls','useful_hours_15','useful_hours_30','useful_hours_60','bus_useful_hours_15','bus_useful_hours_30','bus_useful_hours_60']:\n   disconnected[c]=0\n  for c in df.columns:\n   if c not in disconnected.columns: disconnected[c]=np.nan\n  df=pd.concat([df,disconnected[df.columns]],ignore_index=True)\n df['access_15']="""
if needle not in src: raise RuntimeError('block metrics insertion point not found')
src=src.replace(needle,replacement)
# Robust state-boundary membership when spatial joins return duplicate matches.
old_join="joined=gpd.sjoin(points,block_poly,predicate='within',how='left'); stops['in_new_jersey']=joined.GEOID.notna().to_numpy()"
new_join="joined=gpd.sjoin(points,block_poly,predicate='within',how='left'); in_nj=joined.groupby(level=0).GEOID.apply(lambda s:s.notna().any()).reindex(stops.index,fill_value=False); stops['in_new_jersey']=in_nj.to_numpy()"
if old_join not in src: raise RuntimeError('state join block not found')
src=src.replace(old_join,new_join)
# Verify schedule de-duplication against independently aggregated block metrics instead of hard-coding a pass.
marker="validation=[]\ncon.execute(f\"CREATE OR REPLACE VIEW btp AS SELECT * FROM read_parquet('{primary}')\")"
repl="validation=[]\nmetric_lookup=bp.set_index(['reach_block_idx','day']).departures.to_dict()\ncon.execute(f\"CREATE OR REPLACE VIEW btp AS SELECT * FROM read_parquet('{primary}')\")"
if marker not in src: raise RuntimeError('validation setup block not found')
src=src.replace(marker,repl)
old_pass="'operators':w.operators if w is not None else '', 'schedule_check_pass':True})"
new_pass="'operators':w.operators if w is not None else '', 'schedule_check_pass':(int(w.unique_trips) if w is not None else 0)==int(metric_lookup.get((rb,'weekday'),0)) and (int(s.unique_trips) if s is not None else 0)==int(metric_lookup.get((rb,'saturday'),0))})"
if old_pass not in src: raise RuntimeError('schedule pass block not found')
src=src.replace(old_pass,new_pass)
patched=Path('work/aggregate_accessibility_effective.py'); patched.parent.mkdir(parents=True,exist_ok=True); patched.write_text(src)
Path('out/reproducibility').mkdir(parents=True,exist_ok=True); Path('out/reproducibility/aggregate_accessibility.py').write_text(src)
exec(compile(src,str(patched),'exec'),{'__name__':'__main__','__file__':str(patched)})
