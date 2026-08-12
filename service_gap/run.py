#!/usr/bin/env python3
from pathlib import Path
import base64, gzip, hashlib
parts = [Path(f"service_gap/parts/part{i}.txt").read_text().strip() for i in range(4)]
payload = "".join(parts)
assert hashlib.sha256(payload.encode()).hexdigest() == "dfed5716a714479806681ee687d983adae8ee40ea2a54a64ed2992182f8f80de", "payload checksum mismatch"
source = gzip.decompress(base64.b64decode(payload))
assert hashlib.sha256(source).hexdigest() == "aad9e196181487578ab298b2ca934209d28810daa97114e343fa91d3ad169387", "source checksum mismatch"
path = Path("service_gap/build_accessible_service_and_gap.py")
path.write_bytes(source)
code = compile(source, str(path), "exec")
exec(code, {"__name__": "__main__", "__file__": str(path)})
