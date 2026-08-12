#!/usr/bin/env python3
import inspect
import numpy as np
import pandas as pd
import pandana as pdna

print('pandana', getattr(pdna, '__version__', 'unknown'))
print('Network methods', [m for m in dir(pdna.Network) if 'range' in m.lower() or 'poi' in m.lower() or 'node' in m.lower()])
node_x = pd.Series([0.0, 1.0, 2.0], index=[10,11,12])
node_y = pd.Series([0.0, 0.0, 0.0], index=[10,11,12])
edge_from = pd.Series([10,11])
edge_to = pd.Series([11,12])
edge_weights = pd.DataFrame({'distance':[100.0,100.0]})
net = pdna.Network(node_x,node_y,edge_from,edge_to,edge_weights,twoway=True)
print('get_node_ids', net.get_node_ids(pd.Series([0.1,1.9]),pd.Series([0.0,0.0])).tolist())
if hasattr(net,'nodes_in_range'):
    print('nodes_in_range sig', inspect.signature(net.nodes_in_range))
    print(net.nodes_in_range(pd.Series([10,12]),150).head(20).to_string())
net.precompute(300)
net.set_pois('stops',300,10,pd.Series([2.0],index=['s1']),pd.Series([0.0],index=['s1']))
print(net.nearest_pois(300,'stops',num_pois=10,include_poi_ids=True).to_string())
