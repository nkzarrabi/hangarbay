"""Named FAA fields remain strings; normalization is an explicit projection.

Source dictionaries preserve every named column, including unknown future fields,
after trimming surrounding whitespace. They are not a byte-for-byte archive.
MASTER membership does not imply valid registration or operating authority.
"""
import csv
import hashlib
import io
import re
import tempfile
import zipfile
from urllib.request import Request, urlopen

FAA_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
MAX_MEMBER_BYTES = 2 * 1024**3
MAX_ARCHIVE_BYTES = 160 * 1024**2


def member_name(zf, basename):
    matches = [n for n in zf.namelist() if n.rsplit("/", 1)[-1].upper() == basename.upper()]
    if len(matches) != 1:
        raise ValueError(f"FAA archive missing or ambiguous {basename}")
    if zf.getinfo(matches[0]).file_size > MAX_MEMBER_BYTES:
        raise ValueError(f"FAA member exceeds safety limit: {basename}")
    return matches[0]


def read_rows(zf, basename, required=()):
    """Stream named string fields, rejecting broken/ambiguous headers and rows."""
    with zf.open(member_name(zf, basename)) as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig", errors="strict", newline="") as handle:
            reader = csv.reader(handle)
            header = [" ".join(h.strip().upper().split()) for h in next(reader, [])]
            named = [h for h in header if h]
            if not named or len(named) != len(set(named)) or not set(required).issubset(named):
                raise ValueError(f"Invalid FAA {basename} header; required: {', '.join(required)}")
            for row in reader:
                if not row:
                    continue
                # FAA files can have an unnamed trailing CSV column.
                if len(row) < len(named) or any(v.strip() for v in row[len(header):]):
                    raise ValueError(f"Malformed FAA {basename} row {reader.line_num}")
                if any(v.strip() for h, v in zip(header, row) if not h):
                    raise ValueError(f"Unnamed data in FAA {basename} row {reader.line_num}")
                yield {h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(header) if h}


def load_reference(zf, basename="ACFTREF.txt", *, optional=False):
    if optional and not any(n.rsplit("/", 1)[-1].upper() == basename.upper() for n in zf.namelist()):
        return {}
    result = {}
    for row in read_rows(zf, basename, ("CODE", "MFR", "MODEL")):
        code = row["CODE"]
        if not code:
            continue
        if code in result:
            raise ValueError(f"Duplicate FAA {basename} code: {code}")
        result[code] = row
    return result


def n_number(value):
    value = value.strip().upper()
    value = value if value.startswith("N") else "N" + value
    return value if len(value) <= 6 and re.fullmatch(r"N[1-9][0-9]{0,4}[A-HJ-NP-Z]{0,2}", value) else ""


def iter_aircraft(zf, aircraft_reference=None, *, kind="current", audit=None):
    """Yield joined records; deregistered records require an explicit kind."""
    if kind not in ("current", "deregistered"):
        raise ValueError("kind must be current or deregistered")
    refs = load_reference(zf) if aircraft_reference is None else aircraft_reference
    engines = load_reference(zf, "ENGINE.txt", optional=True)
    audit = audit if audit is not None else {}
    audit.update(input_rows=0, accepted_rows=0, rejected_rows=0, owner_unavailable_rows=0,
                 missing_aircraft_reference_rows=0, missing_engine_reference_rows=0, rejection_reasons={})
    filename = "MASTER.txt" if kind == "current" else "DEREG.txt"
    for raw in read_rows(zf, filename, ("N-NUMBER", "SERIAL NUMBER", "MFR MDL CODE", "NAME")):
        audit["input_rows"] += 1
        tail = n_number(raw["N-NUMBER"])
        if not tail:
            audit["rejected_rows"] += 1
            audit["rejection_reasons"]["invalid_tail"] = audit["rejection_reasons"].get("invalid_tail", 0) + 1
            continue
        reference = refs.get(raw["MFR MDL CODE"], {})
        engine = engines.get(raw.get("ENG MFR MDL", ""), {})
        audit["owner_unavailable_rows"] += not bool(raw["NAME"])
        audit["missing_aircraft_reference_rows"] += not bool(reference)
        audit["missing_engine_reference_rows"] += bool(raw.get("ENG MFR MDL")) and not bool(engine)
        audit["accepted_rows"] += 1
        yield {"n_number": tail, "record_kind": kind, "master": raw,
               "aircraft_reference": reference, "engine_reference": engine}


class RegistryArchive:
    """Own a ZIP reader; caller retains ownership of a supplied file object."""
    def __init__(self, source):
        self.zf = zipfile.ZipFile(source)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.zf.close()

    def records(self, *, kind="current", audit=None):
        return iter_aircraft(self.zf, kind=kind, audit=audit)


def download_archive(*, timeout=90, max_bytes=MAX_ARCHIVE_BYTES):
    """Explicit bounded download. Caller must close the returned seekable file."""
    handle = tempfile.TemporaryFile()
    try:
        request = Request(FAA_URL, headers={"User-Agent": "HangarBay-FAA/0.1", "Accept": "application/zip"})
        digest = hashlib.sha256()
        total = 0
        with urlopen(request, timeout=timeout) as response:
            while chunk := response.read(1024**2):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("FAA download exceeds safety limit")
                digest.update(chunk)
                handle.write(chunk)
        handle.seek(0)
        return handle, {"source_url": FAA_URL, "sha256": digest.hexdigest(), "bytes": total}
    except BaseException:
        handle.close()
        raise
