#!/usr/bin/env python3
from pathlib import Path
import base64, gzip, hashlib

parts = [Path(f"service_gap/parts/part{i}.txt").read_text().strip() for i in range(4)]
payload = "".join(parts)
target = "aad9e196181487578ab298b2ca934209d28810daa97114e343fa91d3ad169387"
print({"part_chars": [len(p) for p in parts], "payload_chars": len(payload), "payload_sha256": hashlib.sha256(payload.encode()).hexdigest()})

source = None
repair_index = None
boundaries = [0, len(parts[0])-2, len(parts[0])-1, len(parts[0]), len(parts[0])+1,
              len(parts[0])+len(parts[1])-2, len(parts[0])+len(parts[1])-1,
              len(parts[0])+len(parts[1]), len(parts[0])+len(parts[1])+1,
              len(parts[0])+len(parts[1])+len(parts[2])-2,
              len(parts[0])+len(parts[1])+len(parts[2])-1,
              len(parts[0])+len(parts[1])+len(parts[2]), len(payload)-1]
seen=set()
for i in boundaries + list(range(len(payload))):
    if i in seen or i < 0 or i >= len(payload):
        continue
    seen.add(i)
    candidate = payload[:i] + payload[i+1:]
    try:
        decoded = gzip.decompress(base64.b64decode(candidate, validate=True))
    except Exception:
        continue
    if hashlib.sha256(decoded).hexdigest() == target:
        source = decoded
        repair_index = i
        break
if source is None:
    raise RuntimeError("Could not recover the checksum-verified source")

text = source.decode("utf-8")
old_acs = '''acs_url = DATA_URLS["acs_2024"] + "?" + urllib.parse.urlencode({
        "get": "NAME,B01003_001E,B11001_001E,B08301_001E,B08301_010E,B08201_002E,B08201_008E",
        "for": "tract:*",
        "in": "state:34",
    }, safe=":,*")'''
new_acs = '''acs_url = DATA_URLS["acs_2024"] + "?" + urllib.parse.urlencode([
        ("get", "NAME,B01003_001E,B11001_001E,B08301_001E,B08301_010E,B08201_002E,B08201_008E"),
        ("for", "tract:*"),
        ("in", "state:34"),
        ("in", "county:*"),
    ], safe=":,*")'''
old_pl = '''url = DATA_URLS["pl_2020"] + "?" + urllib.parse.urlencode({
            "get": "NAME,P1_001N",
            "for": "block:*",
            "in": f"state:34 county:{county} tract:*",
        }, safe=":,* ")'''
new_pl = '''url = DATA_URLS["pl_2020"] + "?" + urllib.parse.urlencode([
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
code = compile(patched, str(path), "exec")
exec(code, {"__name__": "__main__", "__file__": str(path)})
