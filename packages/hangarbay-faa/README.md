# HangarBay FAA importer

An independently installable, standard-library-only package within the HangarBay fork.
It does not import the existing DuckDB/Pandas API, create databases, or download on import.

```sh
pip install "hangarbay-faa @ git+https://github.com/nkzarrabi/hangarbay.git@<commit>#subdirectory=packages/hangarbay-faa"
```

```python
from hangarbay_faa import RegistryArchive
audit = {}
with RegistryArchive("ReleasableAircraft.zip") as source:
    for aircraft in source.records(audit=audit):
        # Stable envelope; all named FAA columns retained as trimmed strings.
        print(aircraft["n_number"], aircraft["aircraft_reference"].get("MODEL"))
print(audit)
```

Use `source.records(kind="deregistered")` explicitly for DEREG history; never
treat it as the current fleet. Keep serial numbers and FAA UNIQUE ID alongside tails:
N-numbers can be reassigned. Missing owner names remain missing; valid aircraft
still appear in the results. No missing identity is reconstructed.

MASTER, ACFTREF and ENGINE fields are preserved, including future named columns.
Missing engine files/references are represented by empty dictionaries. Duplicate
references, ambiguous members, invalid headers, malformed rows and decoding errors
fail rather than produce a misleading snapshot. Invalid N-numbers are counted and
rejected. Dates, reference weight categories, Mode S codes, certification and
registration status remain source strings; no implied eligibility or unit conversion.

FAA semantics: TYPE AIRCRAFT is not airworthiness class; CERTIFICATION carries
airworthiness/operation codes. AC-WEIGHT is a category, not actual aircraft weight.
ENGINE THRUST is not cylinder count. Other names are not automatically operator DBAs.

`download_archive()` is an explicit bounded download returning an owned temporary
file and its exact SHA-256; close that file after use. The archive reader never
extracts paths to disk. Applications own scheduling, atomic snapshot replacement,
retention, searchable projections and Part 135 relationships.

Source: [FAA releasable database and documentation](https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download).
The FAA updates the download daily; fields may legitimately be blank or withheld.
This release does not claim live-data coverage has been validated, and does not
ingest dealer, reserved-number or document-index records as aircraft.

Test installed package: `python -m unittest discover -s packages/hangarbay-faa/tests -v`.
