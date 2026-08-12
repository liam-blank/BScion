#!/usr/bin/env python3
from pathlib import Path
import base64, gzip, hashlib

parts = [Path(f"service_gap/parts/part{i}.txt").read_text().strip() for i in range(4)]
print({"part_chars": [len(p) for p in parts], "part_sha256": [hashlib.sha256(p.encode()).hexdigest() for p in parts]})
# Each repository part is an independently padded base64 segment of the gzip stream.
packed_parts = [base64.b64decode(p, validate=True) for p in parts]
packed = b"".join(packed_parts)
source = gzip.decompress(packed)
source_sha = hashlib.sha256(source).hexdigest()
print({"packed_part_bytes": [len(p) for p in packed_parts], "packed_bytes": len(packed), "source_bytes": len(source), "source_sha256": source_sha})
assert source_sha == "aad9e196181487578ab298b2ca934209d28810daa97114e343fa91d3ad169387", "source checksum mismatch"
path = Path("service_gap/build_accessible_service_and_gap.py")
path.write_bytes(source)
code = compile(source, str(path), "exec")
exec(code, {"__name__": "__main__", "__file__": str(path)})
