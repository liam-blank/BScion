#!/usr/bin/env python3
from pathlib import Path
import base64, gzip, hashlib

parts = [Path(f"service_gap/parts/part{i}.txt").read_text().strip() for i in range(4)]
payload = "".join(parts)
target = "aad9e196181487578ab298b2ca934209d28810daa97114e343fa91d3ad169387"
source = None
repair_index = None
for i in range(len(payload)):
    try:
        decoded = gzip.decompress(base64.b64decode(payload[:i] + payload[i+1:], validate=True))
    except Exception:
        continue
    if hashlib.sha256(decoded).hexdigest() == target:
        source, repair_index = decoded, i
        break
if source is None:
    raise RuntimeError("Could not recover the checksum-verified source")

text = source.decode("utf-8")
old_acs = '''    # 2024 ACS tract totals used by the existing two-factor score and block scaling.
    acs_url = DATA_URLS["acs_2024"] + "?" + urllib.parse.urlencode({
        "get": "NAME,B01003_001E,B11001_001E,B08301_001E,B08301_010E,B08201_002E,B08201_008E",
        "for": "tract:*",
        "in": "state:34",
    }, safe=":,*")
    acs_json = read_json_url(acs_url)
    acs = pd.DataFrame(acs_json[1:], columns=acs_json[0])
    acs["GEOID"] = acs.state + acs.county + acs.tract
    rename = {
        "B01003_001E": "pop_2024",
        "B11001_001E": "households_2024",
        "B08301_001E": "workers16plus",
        "B08301_010E": "transit_commuters",
        "B08201_002E": "hh_zero_vehicle",
        "B08201_008E": "hh_one_vehicle",
    }
    acs = acs.rename(columns=rename)
    for c in rename.values():
        acs[c] = pd.to_numeric(acs[c], errors="coerce").clip(lower=0)
    acs.to_csv(out / "acs_2024_tract_inputs.csv", index=False)
    source_log.append({"dataset": "ACS 2020-2024 five-year estimates", "url": acs_url, "retrieved_at": utcnow(), "use": "tract population, occupied households, and behavioral context"})

'''
new_acs = '''    # 2024 ACS tract totals used by the existing two-factor score and block scaling.
    # Retrieve one county at a time to avoid Census API response-size and wildcard failures.
    county_codes = sorted(blocks.GEOID20.str.slice(2, 5).unique())
    acs_parts = []
    acs_urls = []
    for county in county_codes:
        acs_url = DATA_URLS["acs_2024"] + "?" + urllib.parse.urlencode([
            ("get", "NAME,B01003_001E,B11001_001E,B08301_001E,B08301_010E,B08201_002E,B08201_008E"),
            ("for", "tract:*"),
            ("in", "state:34"),
            ("in", f"county:{county}"),
        ], safe=":,*")
        acs_json = read_json_url(acs_url)
        acs_parts.append(pd.DataFrame(acs_json[1:], columns=acs_json[0]))
        acs_urls.append(acs_url)
    acs = pd.concat(acs_parts, ignore_index=True)
    acs["GEOID"] = acs.state + acs.county + acs.tract
    rename = {
        "B01003_001E": "pop_2024",
        "B11001_001E": "households_2024",
        "B08301_001E": "workers16plus",
        "B08301_010E": "transit_commuters",
        "B08201_002E": "hh_zero_vehicle",
        "B08201_008E": "hh_one_vehicle",
    }
    acs = acs.rename(columns=rename)
    for c in rename.values():
        acs[c] = pd.to_numeric(acs[c], errors="coerce").clip(lower=0)
    acs.to_csv(out / "acs_2024_tract_inputs.csv", index=False)
    source_log.append({"dataset": "ACS 2020-2024 five-year estimates", "url": "; ".join(acs_urls), "retrieved_at": utcnow(), "use": "tract population, occupied households, and behavioral context"})

'''
old_pl = '''        url = DATA_URLS["pl_2020"] + "?" + urllib.parse.urlencode({
            "get": "NAME,P1_001N",
            "for": "block:*",
            "in": f"state:34 county:{county} tract:*",
        }, safe=":,* ")'''
new_pl = '''        url = DATA_URLS["pl_2020"] + "?" + urllib.parse.urlencode([
            ("get", "NAME,P1_001N"),
            ("for", "block:*"),
            ("in", "state:34"),
            ("in", f"county:{county}"),
            ("in", "tract:*"),
        ], safe=":,*")'''
if old_acs not in text or old_pl not in text:
    raise RuntimeError("Expected Census query blocks were not found in recovered source")
text = text.replace(old_acs, new_acs).replace(old_pl, new_pl)
patched = text.encode("utf-8")
print({"repair_index": repair_index, "removed_character": payload[repair_index], "original_source_sha256": target, "patched_source_sha256": hashlib.sha256(patched).hexdigest()})
path = Path("service_gap/build_accessible_service_and_gap.py")
path.write_bytes(patched)
exec(compile(patched, str(path), "exec"), {"__name__": "__main__", "__file__": str(path)})
