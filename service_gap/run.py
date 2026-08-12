#!/usr/bin/env python3
from pathlib import Path
import base64, gzip, hashlib

parts = [Path(f"service_gap/parts/part{i}.txt").read_text().strip() for i in range(4)]
payload = "".join(parts)
target = "aad9e196181487578ab298b2ca934209d28810daa97114e343fa91d3ad169387"
print({"part_chars": [len(p) for p in parts], "payload_chars": len(payload), "payload_sha256": hashlib.sha256(payload.encode()).hexdigest()})

# The repository transfer introduced one extra base64 character. Recover the
# original gzip stream only when the decoded source matches its recorded SHA-256.
source = None
repair_index = None
candidates = []
boundaries = [0, len(parts[0])-2, len(parts[0])-1, len(parts[0]), len(parts[0])+1,
              len(parts[0])+len(parts[1])-2, len(parts[0])+len(parts[1])-1,
              len(parts[0])+len(parts[1]), len(parts[0])+len(parts[1])+1,
              len(parts[0])+len(parts[1])+len(parts[2])-2,
              len(parts[0])+len(parts[1])+len(parts[2])-1,
              len(parts[0])+len(parts[1])+len(parts[2]),
              len(payload)-1]
seen=set()
for i in boundaries + list(range(len(payload))):
    if i in seen or i < 0 or i >= len(payload):
        continue
    seen.add(i)
    candidate = payload[:i] + payload[i+1:]
    try:
        packed = base64.b64decode(candidate, validate=True)
        decoded = gzip.decompress(packed)
    except Exception:
        continue
    digest = hashlib.sha256(decoded).hexdigest()
    candidates.append((i, digest, len(decoded)))
    if digest == target:
        source = decoded
        repair_index = i
        break
if source is None:
    raise RuntimeError(f"Could not recover recorded source; successful candidates={candidates[:10]}")
print({"repair_index": repair_index, "removed_character": payload[repair_index], "source_bytes": len(source), "source_sha256": hashlib.sha256(source).hexdigest()})
path = Path("service_gap/build_accessible_service_and_gap.py")
path.write_bytes(source)
code = compile(source, str(path), "exec")
exec(code, {"__name__": "__main__", "__file__": str(path)})
