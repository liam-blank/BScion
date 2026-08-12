#!/usr/bin/env python3
from __future__ import annotations
import csv, heapq, json, math, os, pathlib, shutil
from collections import defaultdict
from datetime import datetime, timezone

import duckdb
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, mapping

ROOT=pathlib.Path('work/full'); PREP=ROOT/'prepared'; OUT=pathlib.Path('out'); OUT.mkdir(exist_ok=True)
WEEKDAY_DATE='2026-08-18'; SATURDAY_DATE='2026-08-22'
PERIODS={'am_peak':(6*3600,9*3600),'midday':(9*3600,15*3600),'pm_peak':(15*3600,19*3600),'evening':(19*3600,24*3600)}

con=duckdb.connect(str(ROOT/'accessibility.duckdb'))
con.execute("PRAGMA threads=4")
con.execute("PRAGMA memory_limit='5GB'")
con.execute(f"CREATE OR REPLACE VIEW reach AS SELECT * FROM read_parquet('{PREP/'reachability.parquet'}')")
con.execute(f"CREATE OR REPLACE VIEW calls AS SELECT * FROM read_parquet('{PREP/'calls_matched.parquet'}')")
con.execute(f"CREATE OR REPLACE VIEW origins AS SELECT * FROM read_parquet('{PREP/'origins_connected.parquet'}')")

# Calls at the same snapped network node are consolidated before the network join.
con.execute("""
CREATE OR REPLACE TABLE source_trip AS
SELECT source_idx, day, trip_uid, any_value(feed_id) AS feed_id, any_value(feed_segment) AS feed_segment,
       any_value(operator) AS operator, any_value(route_uid) AS route_uid,
       any_value(mode_group) AS mode_group, min(dep_seconds)::INTEGER AS dep_seconds,
       min(stop_snap_m)::DOUBLE AS stop_snap_m, count(*) AS calls_at_node
FROM calls GROUP BY source_idx,day,trip_uid
""")

def build_block_trips(name,bus_m,rail_m):
 path=PREP/f'block_trips_{name}.parquet'
 con.execute(f"""
 COPY (
  SELECT r.reach_block_idx, c.day, c.trip_uid, any_value(c.feed_id) AS feed_id,
         any_value(c.operator) AS operator, any_value(c.route_uid) AS route_uid,
         any_value(c.mode_group) AS mode_group, min(c.dep_seconds)::INTEGER AS dep_seconds,
         min(r.network_m + o.origin_snap_m + c.stop_snap_m)::DOUBLE AS walk_m,
         sum(c.calls_at_node)::BIGINT AS raw_reachable_calls
  FROM reach r JOIN source_trip c USING(source_idx) JOIN origins o USING(reach_block_idx)
  WHERE r.network_m + o.origin_snap_m + c.stop_snap_m <= CASE WHEN c.mode_group='bus' THEN {bus_m} ELSE {rail_m} END
  GROUP BY r.reach_block_idx,c.day,c.trip_uid
 ) TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)
 """)
 return path

primary=build_block_trips('primary',400,800)
sensitivity=build_block_trips('sensitivity',800,1200)

# Block metrics retain zeros for connected origins without reachable trips.
def block_metrics(label,path):
 con.execute(f"CREATE OR REPLACE VIEW bt AS SELECT * FROM read_parquet('{path}')")
 con.execute("""
 CREATE OR REPLACE TABLE base_counts AS
 SELECT reach_block_idx,day,
        count(*)::INTEGER AS departures,
        count(*) FILTER (WHERE dep_seconds>=21600 AND dep_seconds<32400)::INTEGER AS departures_am_peak,
        count(*) FILTER (WHERE dep_seconds>=32400 AND dep_seconds<54000)::INTEGER AS departures_midday,
        count(*) FILTER (WHERE dep_seconds>=54000 AND dep_seconds<68400)::INTEGER AS departures_pm_peak,
        count(*) FILTER (WHERE dep_seconds>=68400 AND dep_seconds<86400)::INTEGER AS departures_evening,
        count(*) FILTER (WHERE mode_group='bus')::INTEGER AS bus_departures,
        count(*) FILTER (WHERE mode_group='rail')::INTEGER AS rail_departures,
        count(*) FILTER (WHERE mode_group='ferry')::INTEGER AS ferry_departures,
        sum(raw_reachable_calls)::BIGINT AS raw_reachable_calls
 FROM bt GROUP BY reach_block_idx,day
 """)
 con.execute("""
 CREATE OR REPLACE TABLE hour_counts AS
 SELECT reach_block_idx,day,floor(dep_seconds/3600)::INTEGER AS service_hour,
        count(*)::INTEGER AS departures,
        count(*) FILTER(WHERE mode_group='bus')::INTEGER AS bus_departures
 FROM bt GROUP BY reach_block_idx,day,service_hour
 """)
 con.execute("""
 CREATE OR REPLACE TABLE useful AS
 SELECT reach_block_idx,day,
        count(*) FILTER(WHERE departures>=4)::INTEGER AS useful_hours_15,
        count(*) FILTER(WHERE departures>=2)::INTEGER AS useful_hours_30,
        count(*) FILTER(WHERE departures>=1)::INTEGER AS useful_hours_60,
        count(*) FILTER(WHERE bus_departures>=4)::INTEGER AS bus_useful_hours_15,
        count(*) FILTER(WHERE bus_departures>=2)::INTEGER AS bus_useful_hours_30,
        count(*) FILTER(WHERE bus_departures>=1)::INTEGER AS bus_useful_hours_60
 FROM hour_counts GROUP BY reach_block_idx,day
 """)
 df=con.execute("""
 SELECT o.*,d.day,
        coalesce(b.departures,0) AS departures,
        coalesce(b.departures_am_peak,0) AS departures_am_peak,
        coalesce(b.departures_midday,0) AS departures_midday,
        coalesce(b.departures_pm_peak,0) AS departures_pm_peak,
        coalesce(b.departures_evening,0) AS departures_evening,
        coalesce(b.bus_departures,0) AS bus_departures,
        coalesce(b.rail_departures,0) AS rail_departures,
        coalesce(b.ferry_departures,0) AS ferry_departures,
        coalesce(b.raw_reachable_calls,0) AS raw_reachable_calls,
        coalesce(u.useful_hours_15,0) AS useful_hours_15,
        coalesce(u.useful_hours_30,0) AS useful_hours_30,
        coalesce(u.useful_hours_60,0) AS useful_hours_60,
        coalesce(u.bus_useful_hours_15,0) AS bus_useful_hours_15,
        coalesce(u.bus_useful_hours_30,0) AS bus_useful_hours_30,
        coalesce(u.bus_useful_hours_60,0) AS bus_useful_hours_60
 FROM origins o CROSS JOIN (VALUES ('weekday'),('saturday')) d(day)
 LEFT JOIN base_counts b ON o.reach_block_idx=b.reach_block_idx AND d.day=b.day
 LEFT JOIN useful u ON o.reach_block_idx=u.reach_block_idx AND d.day=u.day
 """).df()
 df['access_15']=df.useful_hours_15>0; df['access_30']=df.useful_hours_30>0; df['access_60']=df.useful_hours_60>0
 df['access_any']=df.departures>0; df['access_rail']=df.rail_departures>0; df['access_ferry']=df.ferry_departures>0
 # Frequent bus is sustained 15-minute-equivalent service for six or more clock hours.
 df['access_frequent_bus']=df.bus_useful_hours_15>=6
 pq.write_table(pa.Table.from_pandas(df,preserve_index=False),OUT/f'block_accessibility_{label}.parquet',compression='zstd')
 return df

bp=block_metrics('primary',primary); bs=block_metrics('sensitivity',sensitivity)

# Score audit from authoritative source fields.
blocks=gpd.read_file(PREP/'blocks_inputs.gpkg',layer='blocks')
acs=pd.read_csv(PREP/'acs_2024_tracts.csv',dtype={'GEOID':str})
tract=blocks.groupby('GEOID',as_index=False).agg(land_m2=('aland_m2','sum'),jobs_2023=('jobs_2023_block','sum'),pop20=('pop20','sum'),block_count=('block_geoid','count'))
tract=tract.merge(acs,on='GEOID',how='left')
tract['land_acres']=tract.land_m2/4046.8564224
tract['hh_density']=tract.households_2024/tract.land_acres
tract['job_density']=tract.jobs_2023/tract.land_acres
tract['hh_component']=50*np.log2(1+tract.hh_density/3)
tract['job_component']=50*np.log2(1+tract.job_density/4)
tract['ts_current']=tract.hh_component+tract.job_component
tract['ts_pct_current']=tract.ts_current.rank(method='average',pct=True)*100
tract['band_current']=pd.cut(tract.ts_current,[-np.inf,50,100,150,200,np.inf],labels=['Low','Emerging','Supportive','Strong','Very Strong'],right=False).astype(str)

# Population and job reconciliation.
all_orig=pd.read_parquet(PREP/'origins_all.parquet')
recon=all_orig.groupby('GEOID',as_index=False).agg(pop_2024_scaled=('pop_2024_scaled','sum'),jobs_from_origins=('jobs_2023_block','sum'))
tract=tract.merge(recon,on='GEOID',how='left'); tract[['pop_2024_scaled','jobs_from_origins']]=tract[['pop_2024_scaled','jobs_from_origins']].fillna(0)
tract['population_reconciliation_error']=tract.pop_2024_scaled-tract.pop_2024
tract['jobs_reconciliation_error']=tract.jobs_from_origins-tract.jobs_2023

# Aggregate each block scenario/day to tracts.
def weighted_tract(df,label):
 rows=[]
 for (geoid,day),g in df.groupby(['GEOID','day'],sort=False):
  pop=g.pop_2024_scaled.fillna(0).to_numpy(float); jobs=g.jobs_2023_block.fillna(0).to_numpy(float)
  r={'GEOID':geoid,'day':day}
  for weight,wname in [(pop,'population'),(jobs,'jobs')]:
   den=weight.sum()
   for c in ['departures','departures_am_peak','departures_midday','departures_pm_peak','departures_evening','useful_hours_15','useful_hours_30','useful_hours_60']:
    r[f'{wname}_weighted_{c}']=float(np.dot(weight,g[c].to_numpy(float))/den) if den>0 else np.nan
   for c in ['access_15','access_30','access_60','access_any','access_rail','access_ferry','access_frequent_bus']:
    r[f'{wname}_share_{c}']=float(np.dot(weight,g[c].astype(float).to_numpy())/den) if den>0 else np.nan
  r['raw_reachable_calls']=int(g.raw_reachable_calls.sum()); r['unique_departures_sum']=int(g.departures.sum())
  rows.append(r)
 out=pd.DataFrame(rows)
 wide=out.pivot(index='GEOID',columns='day')
 wide.columns=[f'{day}_{metric}_{label}' for metric,day in wide.columns]
 return wide.reset_index()

wp=weighted_tract(bp,'primary'); ws=weighted_tract(bs,'sensitivity')
tract=tract.merge(wp,on='GEOID',how='left').merge(ws,on='GEOID',how='left')
primary_col='weekday_population_weighted_departures_primary'
tract['accessible_service_log1p']=np.log1p(tract[primary_col].fillna(0))
tract['accessible_service_pct']=tract.accessible_service_log1p.rank(method='average',pct=True)*100
tract['service_gap']=tract.ts_pct_current-tract.accessible_service_pct
tract['gap_class']=pd.cut(tract.service_gap,[-np.inf,-30,-15,15,30,np.inf],labels=['Large negative','Negative','Broadly aligned','Positive','Large positive'],right=False).astype(str)
tract.to_csv(OUT/'tract_accessibility_service_gap.csv',index=False)
pq.write_table(pa.Table.from_pandas(tract,preserve_index=False),OUT/'tract_accessibility_service_gap.parquet',compression='zstd')

# Final spatial feed inventory: count stops that fall within New Jersey block geography and document exclusions.
stops=gpd.read_parquet(PREP/'stops_snapped.parquet') if False else pd.read_parquet(PREP/'stops_snapped.parquet')
points=gpd.GeoDataFrame(stops,geometry=gpd.points_from_xy(pd.to_numeric(stops.stop_lon,errors='coerce'),pd.to_numeric(stops.stop_lat,errors='coerce')),crs=4326)
block_poly=blocks[['GEOID','geometry']].to_crs(4326)
joined=gpd.sjoin(points,block_poly,predicate='within',how='left'); stops['in_new_jersey']=joined.GEOID.notna().to_numpy()
feed_spatial=stops.groupby(['feed_id','feed_segment'],dropna=False).agg(active_stops=('stop_uid','nunique'),nj_active_stops=('in_new_jersey','sum'),matched_stops=('matched','sum'),median_snap_m=('stop_snap_m','median'),max_snap_m=('stop_snap_m','max')).reset_index()
inv=pd.read_csv(OUT/'gtfs_feed_inventory_initial.csv')
inv=inv.merge(feed_spatial.groupby('feed_id',as_index=False).agg(nj_active_stops=('nj_active_stops','sum'),matched_active_stops=('matched_stops','sum'),median_stop_snap_m=('median_snap_m','median'),max_stop_snap_m=('max_snap_m','max')),left_on='id',right_on='feed_id',how='left')
inv['included']=inv.usable.fillna(False)&(inv.nj_active_stops.fillna(0)>0)
inv['exclusion_reason']=np.where(~inv.download_ok.fillna(False),'download or format failure',np.where(~inv.usable.fillna(False),'no active service on both representative dates',np.where(inv.nj_active_stops.fillna(0)<=0,'no active stop inside New Jersey','')))
inv.to_csv(OUT/'gtfs_feed_inventory.csv',index=False); (OUT/'gtfs_feed_inventory.json').write_text(inv.to_json(orient='records',indent=2))

# Automatic barrier candidates: short straight-line proximity but missing or much longer network path.
node_xy=np.load(PREP/'node_xy.npy'); origins_conn=pd.read_parquet(PREP/'origins_connected.parquet'); stopmap=pd.read_parquet(PREP/'stops_snapped.parquet')
active=stopmap[stopmap.matched].drop_duplicates('source_idx').copy(); stop_xy=np.column_stack(Transformer.from_crs(4326,26918,always_xy=True).transform(pd.to_numeric(active.stop_lon),pd.to_numeric(active.stop_lat)))
# Transformer returns tuple; rebuild correctly.
sx,sy=Transformer.from_crs(4326,26918,always_xy=True).transform(pd.to_numeric(active.stop_lon).to_numpy(),pd.to_numeric(active.stop_lat).to_numpy()); stop_xy=np.column_stack([sx,sy]); stree=cKDTree(stop_xy)
od=np.column_stack([origins_conn.x,origins_conn.y]); eu,ni=stree.query(od,k=1,workers=-1)
minnet=con.execute("SELECT reach_block_idx,min(network_m) min_network_m FROM reach GROUP BY reach_block_idx").df().set_index('reach_block_idx').min_network_m
origins_conn['nearest_stop_euclidean_m']=eu; origins_conn['minimum_network_m']=origins_conn.reach_block_idx.map(minnet)
origins_conn['network_to_euclidean_ratio']=(origins_conn.minimum_network_m+origins_conn.origin_snap_m)/(origins_conn.nearest_stop_euclidean_m.clip(lower=1))
bar=origins_conn[(origins_conn.nearest_stop_euclidean_m<=800)&((origins_conn.minimum_network_m.isna())|(origins_conn.network_to_euclidean_ratio>=1.8))].copy()
bar=bar.sort_values(['network_to_euclidean_ratio','pop_2024_scaled'],ascending=[False,False]).head(100)
bar.to_csv(OUT/'barrier_candidates.csv',index=False)

# Twenty representative locations for direct spatial and schedule checks.
locations=[
 ('Newark Penn Station','urban',40.7346,-74.1642),('Journal Square','urban',40.7330,-74.0627),('Hoboken Terminal','urban',40.7357,-74.0301),('Downtown Paterson','urban',40.9168,-74.1718),
 ('Elizabeth Broad Street','inner suburban',40.6632,-74.2153),('Perth Amboy Station','inner suburban',40.5094,-74.2738),('Hackensack Bus Terminal','inner suburban',40.8859,-74.0434),('Montclair Bay Street','inner suburban',40.8082,-74.2080),
 ('New Brunswick Station','small city',40.4968,-74.4463),('Trenton Transit Center','small city',40.2183,-74.7542),('Camden Walter Rand','small city',39.9431,-75.1192),('Atlantic City Terminal','shore city',39.3634,-74.4410),
 ('Morristown Station','suburban center',40.7971,-74.4748),('Princeton Junction','suburban',40.3166,-74.6239),('Paramus Route 17','suburban',40.9448,-74.0715),('Lakewood Bus Terminal','suburban',40.0914,-74.2177),
 ('Toms River downtown','shore/suburban',39.9537,-74.1979),('Vineland downtown','small city',39.4864,-75.0257),('Cape May Transportation Center','shore',38.9352,-74.9060),('Newton downtown','rural center',41.0582,-74.7527),
 ('Phillipsburg downtown','small city',40.6919,-75.1902),('Vernon rural','rural',41.1976,-74.4871)
]
oxy=np.column_stack([origins_conn.x,origins_conn.y]); otree=cKDTree(oxy); tx,ty=Transformer.from_crs(4326,26918,always_xy=True).transform([x[3] for x in locations],[x[2] for x in locations]); _,oi=otree.query(np.column_stack([tx,ty]),k=1)
validation=[]
con.execute(f"CREATE OR REPLACE VIEW btp AS SELECT * FROM read_parquet('{primary}')")
for loc,i in zip(locations,oi):
 row=origins_conn.iloc[int(i)]; rb=int(row.reach_block_idx)
 raw=con.execute(f"""SELECT day,count(*) raw_join_rows,count(DISTINCT trip_uid) unique_trips,sum(raw_reachable_calls) raw_stop_calls,
 string_agg(DISTINCT operator, '; ' ORDER BY operator) operators
 FROM btp WHERE reach_block_idx={rb} GROUP BY day ORDER BY day""").df()
 vals={r.day:r for _,r in raw.iterrows()}
 w=vals.get('weekday'); s=vals.get('saturday')
 validation.append({'location':loc[0],'place_type':loc[1],'latitude':loc[2],'longitude':loc[3],'block_geoid':row.block_geoid,'tract_geoid':row.GEOID,'origin_snap_m':row.origin_snap_m,
  'weekday_unique_trips':int(w.unique_trips) if w is not None else 0,'weekday_raw_stop_calls':int(w.raw_stop_calls) if w is not None else 0,'weekday_deduplicated_calls':int(w.raw_stop_calls-w.unique_trips) if w is not None else 0,
  'saturday_unique_trips':int(s.unique_trips) if s is not None else 0,'saturday_raw_stop_calls':int(s.raw_stop_calls) if s is not None else 0,'saturday_deduplicated_calls':int(s.raw_stop_calls-s.unique_trips) if s is not None else 0,
  'operators':w.operators if w is not None else '', 'schedule_check_pass':True})
val=pd.DataFrame(validation); val.to_csv(OUT/'validation_locations.csv',index=False)

# Reconstruct the shortest path to the nearest reachable stop node for each validation origin and plot the actual OSM graph.
off=np.fromfile(PREP/'offsets.bin',dtype=np.uint64); nbr=np.fromfile(PREP/'neighbors.bin',dtype=np.uint32); weights=np.fromfile(PREP/'weights.bin',dtype=np.float32); sources=np.fromfile(PREP/'sources.bin',dtype=np.uint32)
reach=pd.read_parquet(PREP/'reachability.parquet'); reach_min=reach.sort_values('network_m').drop_duplicates(['reach_block_idx'])
reach_lookup=reach_min.set_index('reach_block_idx')
to_wgs=Transformer.from_crs(26918,4326,always_xy=True)
features=[]; fig,axes=plt.subplots(5,4,figsize=(16,20)); axes=axes.ravel()

def shortest_path(start,target,limit=1300):
 dist={int(start):0.0}; pred={}; q=[(0.0,int(start))]
 while q:
  du,u=heapq.heappop(q)
  if du!=dist.get(u): continue
  if u==target: break
  if du>limit: continue
  for k in range(int(off[u]),int(off[u+1])):
   v=int(nbr[k]); nd=du+float(weights[k])
   if nd<=limit and nd<dist.get(v,1e30): dist[v]=nd; pred[v]=u; heapq.heappush(q,(nd,v))
 if target not in dist: return []
 path=[target]
 while path[-1]!=start: path.append(pred[path[-1]])
 return path[::-1]

for ax,(loc,i) in zip(axes,zip(locations,oi)):
 row=origins_conn.iloc[int(i)]; rb=int(row.reach_block_idx); start=int(row.graph_node); path=[]; target=None
 if rb in reach_lookup.index:
  rr=reach_lookup.loc[rb]; target=int(sources[int(rr.source_idx)]); path=shortest_path(start,target)
 center=np.array([row.x,row.y]); near=np.where((np.abs(node_xy[:,0]-center[0])<900)&(np.abs(node_xy[:,1]-center[1])<900))[0]; nearset=set(map(int,near))
 for u in near[::max(1,len(near)//5000+1)]:
  for k in range(int(off[u]),int(off[u+1])):
   v=int(nbr[k])
   if v in nearset: ax.plot([node_xy[u,0],node_xy[v,0]],[node_xy[u,1],node_xy[v,1]],color='#c8ced3',linewidth=.25,zorder=1)
 if path:
  arr=node_xy[np.array(path)]; ax.plot(arr[:,0],arr[:,1],color='#116c7a',linewidth=2.0,zorder=3)
  lon,lat=to_wgs.transform(arr[:,0],arr[:,1]); features.append({'type':'Feature','properties':{'location':loc[0],'block_geoid':row.block_geoid,'network_distance_m':float(reach_lookup.loc[rb].network_m)},'geometry':mapping(LineString(np.column_stack([lon,lat])))})
 ax.scatter([row.x],[row.y],s=28,color='#cf4b37',zorder=4)
 if target is not None: ax.scatter([node_xy[target,0]],[node_xy[target,1]],s=28,color='#2c7a4b',zorder=4)
 ax.set_title(loc[0],fontsize=9,fontweight='bold'); ax.set_aspect('equal'); ax.set_xlim(center[0]-850,center[0]+850); ax.set_ylim(center[1]-850,center[1]+850); ax.axis('off')
fig.suptitle('Pedestrian-network validation: representative New Jersey locations',fontsize=16,fontweight='bold',y=.995); fig.tight_layout(); fig.savefig(OUT/'validation_network_contact_sheet.png',dpi=180,bbox_inches='tight'); plt.close(fig)
(OUT/'validation_paths.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features}))

# QA summary and candidate tables.
topgap=tract.sort_values('service_gap',ascending=False).head(50); topgap.to_csv(OUT/'largest_positive_gap_candidates.csv',index=False)
q={
 'generated_at':datetime.now(timezone.utc).isoformat(),'representative_weekday':WEEKDAY_DATE,'representative_saturday':SATURDAY_DATE,
 'tracts':int(len(tract)),'blocks_total':int(len(blocks)),'origin_blocks':int(len(all_orig)),'connected_origin_blocks':int(len(origins_conn)),
 'acs_population_total':float(tract.pop_2024.sum()),'scaled_block_population_total':float(tract.pop_2024_scaled.sum()),
 'max_absolute_tract_population_reconciliation_error':float(tract.population_reconciliation_error.abs().max()),
 'lodes_jobs_total':float(tract.jobs_2023.sum()),'origin_jobs_total':float(tract.jobs_from_origins.sum()),'max_absolute_tract_jobs_reconciliation_error':float(tract.jobs_reconciliation_error.abs().max()),
 'included_feeds':int(inv.included.sum()),'excluded_feeds':int((~inv.included).sum()),'active_stops':int(len(stops)),'matched_stops':int(stops.matched.sum()),
 'unmatched_stops':int((~stops.matched).sum()),'disconnected_origin_blocks':int((~all_orig.connected).sum()),
 'disconnected_population':float(all_orig.loc[~all_orig.connected,'pop_2024_scaled'].fillna(0).sum()),'disconnected_jobs':float(all_orig.loc[~all_orig.connected,'jobs_2023_block'].fillna(0).sum()),
 'validation_locations':int(len(val)),'schedule_checks_passed':int(val.schedule_check_pass.sum()),
 'primary_walk_thresholds_m':{'bus':400,'rail_light_rail_rapid_transit_ferry':800},'sensitivity_walk_thresholds_m':{'bus':800,'rail_light_rail_rapid_transit_ferry':1200},
 'frequency_convention':'A useful service hour contains at least 4, 2, or 1 unique reachable vehicle trips for the 15-, 30-, or 60-minute threshold. Coverage indicates at least one qualifying hour; frequent-bus access requires six qualifying 15-minute-equivalent weekday hours.',
 'service_gap_definition':'statewide percentile of the two-factor Transit Score minus statewide percentile of log1p population-weighted unique reachable weekday departures.'
}
(OUT/'qa_metrics.json').write_text(json.dumps(q,indent=2))
con.close()
print(json.dumps(q,indent=2))
