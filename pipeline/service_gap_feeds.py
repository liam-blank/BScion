from __future__ import annotations

REPRESENTATIVE_TUESDAY = '2026-08-11'
REPRESENTATIVE_SATURDAY = '2026-08-15'

FEEDS = [
 {'id':'njt_bus','operator':'NJ TRANSIT Bus','category':'statewide public transit','urls':['https://www.njtransit.com/bus_data.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-new-jersey-transit-nj-transit-gtfs-508.zip?alt=media']},
 {'id':'njt_rail','operator':'NJ TRANSIT Rail and Light Rail','category':'statewide public transit','urls':['https://www.njtransit.com/rail_data.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-new-jersey-transit-nj-transit-gtfs-509.zip?alt=media']},
 {'id':'path','operator':'PATH','category':'rapid transit','urls':['https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/14843/PATHGTFS.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-port-authority-trans-hudson-path-gtfs-517.zip?alt=media']},
 {'id':'patco','operator':'PATCO Speedline','category':'rapid transit','urls':['https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/13562/PATCO_GTFS.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-patco-speedline-gtfs-3035.zip?alt=media']},
 {'id':'septa_rail','operator':'SEPTA Regional Rail','category':'cross-border rail','urls':['https://www3.septa.org/developer/google_rail.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-pennsylvania-southeastern-pennsylvania-transportation-authority-gtfs-503.zip?alt=media']},
 {'id':'septa_bus','operator':'SEPTA surface transit','category':'cross-border surface transit','urls':['https://www3.septa.org/developer/google_bus.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-pennsylvania-southeastern-pennsylvania-transportation-authority-gtfs-502.zip?alt=media']},
 {'id':'amtrak','operator':'Amtrak','category':'intercity rail','urls':['https://content.amtrak.com/content/gtfs/GTFS.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-unknown-amtrak-gtfs-11.zip?alt=media']},
 {'id':'academy','operator':'Academy Lines','category':'commuter bus','urls':['https://www.njtransit.com/Academy_bus_data.zip']},
 {'id':'coachusa','operator':'Coach USA New Jersey affiliates','category':'commuter bus','urls':['https://api.prod.coachusa.com/gtfs']},
 {'id':'lakeland','operator':'Lakeland Bus Lines','category':'commuter bus','urls':['https://content.njtransit.com/sites/default/files/developers-resources/LakelandBusLines_bus_data.zip']},
 {'id':'boxcar','operator':'Boxcar','category':'commuter bus','urls':['https://boxcar-gtfs.vercel.app/api/gtfs','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-jersey-boxcar-gtfs-3105.zip?alt=media']},
 {'id':'nywaterway','operator':'NY Waterway ferry','category':'ferry','urls':['https://nywaterway.connexionz.net/rtt/public/resource/gtfs.zip','https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-new-york-ny-waterway-gtfs-3192.zip?alt=media']},
 {'id':'nywaterway_bus','operator':'NY Waterway shuttle buses','category':'ferry feeder bus','urls':['https://services.saucontds.com/service-schedule-server/gtfsFeed/749f33f0-b1d7-4be2-b0ea-3f63cf39073e']},
 {'id':'seastreak','operator':'Seastreak','category':'ferry','urls':['https://seastreak.com/api/transit/google_transit.zip']},
 {'id':'princeton','operator':'Princeton University TigerTransit','category':'university transit','urls':['https://princeton.tripshot.com/v1/gtfs.zip']},
 {'id':'rutgers','operator':'Rutgers University Transit','category':'university transit','urls':['https://rutgers.tripshot.com/v1/gtfs.zip']},
 {'id':'gloucester','operator':'Gloucester County transit','category':'county transit','urls':['https://www.njtransit.com/Gloucester_Co_bus_data.zip']},
 {'id':'atlantic_county','operator':'Atlantic County transit','category':'county transit','urls':['https://www.njtransit.com/AtlanticCo_bus_data.zip']},
 {'id':'sjta','operator':'South Jersey Transportation Authority','category':'regional shuttle','urls':['https://www.njtransit.com/SJTA_bus_data.zip']},
 {'id':'cumberland','operator':'Cumberland County transit','category':'county transit','urls':['https://www.njtransit.com/Cumberland_Co_bus_data.zip']},
 {'id':'burlington','operator':'Burlington County BurLINK','category':'county transit','urls':['https://www.njtransit.com/BurlingtonShuttles_bus_data.zip']},
 {'id':'somerset','operator':'Somerset County transit','category':'county transit','urls':['https://www.njtransit.com/SomersetCounty_bus_data.zip']},
 {'id':'hunterdon','operator':'Hunterdon County LINK','category':'county transit','urls':['https://www.njtransit.com/Hunterdon_Co_bus_data.zip']},
 {'id':'broadway','operator':'Broadway Bus Corporation','category':'local bus','urls':['https://www.njtransit.com/broadway_bus_data.zip']},
 {'id':'warren','operator':'Warren County transit','category':'county transit','urls':['https://www.njtransit.com/WCT_bus_data.zip']},
 {'id':'sussex','operator':'Sussex County transit','category':'county transit','urls':['https://www.njtransit.com/sussexcounty_bus_data.zip']},
]

MATERIAL_OMISSIONS = [
 {'operator':'Atlantic City Jitney Association','reason':'No usable public static GTFS schedule feed was located for this analysis.'},
 {'operator':'Ocean County Ocean Ride','reason':'No usable public static GTFS schedule feed was located for the county fixed-route network.'},
 {'operator':'RiverLink Ferry','reason':'No usable public static GTFS schedule feed was located; service is seasonal.'},
 {'operator':'Liberty Landing Ferry','reason':'No usable public static GTFS schedule feed was located.'},
 {'operator':'Hudson County and North Jersey private jitneys','reason':'Routes and stop-level schedules are not represented by a complete authoritative public GTFS feed.'},
]

# GTFS route types grouped for walking thresholds and mode-access reporting.
BUS_ROUTE_TYPES = {3,11,700,701,702,704,705,706,707,708,709,710,711,712,713,714,715,716}
FERRY_ROUTE_TYPES = {4,1000}
RAIL_ROUTE_TYPES = {0,1,2,5,6,7,12,100,101,102,103,106,109,400,401,402,403,404,405}
