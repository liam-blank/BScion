#!/usr/bin/env python3
from pathlib import Path

p = Path('pipeline/full_analysis/prepare_inputs.py')
s = p.read_text()
start = s.index('    # ACS tract controls.')
end = s.index('    # Tract geometry and state analysis boundary.', start)
replacement = '''    # ACS tract controls from Census Reporter. Census Reporter loaded the 2024 ACS five-year release on February 8, 2026.
    acs_url = "https://api.censusreporter.org/1.0/data/show/latest?table_ids=B01003,B11001&geo_ids=140%7C04000US34"
    acs_path = DATA / "acs_2024_tracts.json"
    response = requests.get(acs_url, timeout=240, headers={"User-Agent": UA})
    response.raise_for_status()
    acs_path.write_bytes(response.content)
    payload = response.json()
    geography = payload.get("geography", {})
    rows = []
    for full_geoid, tables in payload.get("data", {}).items():
        if not full_geoid.startswith("14000US"):
            continue
        rows.append({
            "GEOID": full_geoid.replace("14000US", "", 1),
            "NAME": geography.get(full_geoid, {}).get("name", full_geoid),
            "pop_2024": tables.get("B01003", {}).get("estimate", {}).get("B01003001"),
            "households_2024": tables.get("B11001", {}).get("estimate", {}).get("B11001001"),
        })
    acs = pd.DataFrame(rows)
    if len(acs) < 2000:
        raise RuntimeError(f"Census Reporter returned only {len(acs)} New Jersey tracts")
    acs["pop_2024"] = pd.to_numeric(acs["pop_2024"], errors="coerce").fillna(0)
    acs["households_2024"] = pd.to_numeric(acs["households_2024"], errors="coerce").fillna(0)
    source_records.append({
        "dataset": "acs_2024_tracts",
        "url": acs_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "bytes": acs_path.stat().st_size,
        "sha256": sha256(acs_path),
        "http_status": response.status_code,
    })

'''
p.write_text(s[:start] + replacement + s[end:])
print('Replaced Census API tract request with current Census Reporter 2024 ACS data.')
