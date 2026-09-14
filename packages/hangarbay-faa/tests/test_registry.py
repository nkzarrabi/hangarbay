import csv
import io
import sys
import unittest
import zipfile
from unittest.mock import patch
from hangarbay_faa import RegistryArchive

def archive(master=None, reference=None, extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("nested/MASTER.txt", master or
            "N-NUMBER,SERIAL NUMBER,MFR MDL CODE,NAME,ENG MFR MDL,MODE S CODE HEX,OTHER NAMES(1),NEW FIELD\n"
            "123AB,000123,A,,E,00ABCD,SECOND OWNER,retained\n"
            "00001,invalid,A,X,E,,,\n")
        zf.writestr("ACFTREF.txt", reference or "CODE,MFR,MODEL,AC-WEIGHT,NO-SEATS\nA,EXAMPLE,MODEL,1,4\n")
        zf.writestr("ENGINE.txt", "CODE,MFR,MODEL,HORSEPOWER,THRUST\nE,ENGINE CO,TURBINE,0,1250\n")
        for name, content in (extra or {}).items():
            zf.writestr(name, content)
    buffer.seek(0)
    return buffer

class RegistryTests(unittest.TestCase):
    def test_joins_preserve_withheld_owner_and_unknown_fields(self):
        audit = {}
        with RegistryArchive(archive()) as source:
            rows = list(source.records(audit=audit))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["master"]["NAME"], "")
        self.assertEqual(row["master"]["SERIAL NUMBER"], "000123")
        self.assertEqual(row["master"]["MODE S CODE HEX"], "00ABCD")
        self.assertEqual(row["master"]["NEW FIELD"], "retained")
        self.assertEqual(row["engine_reference"]["THRUST"], "1250")
        self.assertEqual(row["aircraft_reference"]["AC-WEIGHT"], "1")
        self.assertEqual(audit["input_rows"], audit["accepted_rows"] + audit["rejected_rows"])
        self.assertEqual(audit["owner_unavailable_rows"], 1)

    def test_invalid_schema_and_duplicate_members_fail_closed(self):
        for source in [archive("WRONG,NAME\n123AB,X\n"),
                       archive(extra={"MASTER.txt": "N-NUMBER,NAME\n123AB,X\n"}),
                       archive(reference="CODE,MFR,MODEL\nA,A,A\nA,B,B\n")]:
            with self.subTest(), RegistryArchive(source) as registry:
                with self.assertRaises(ValueError):
                    list(registry.records())

    def test_missing_reference_is_unknown_and_history_is_separate(self):
        historical = "N-NUMBER,SERIAL NUMBER,MFR MDL CODE,NAME,CANCEL DATE\n123AB,old,UNKNOWN,OLD OWNER,20200101\n"
        with RegistryArchive(archive(extra={"DEREG.txt": historical})) as source:
            current = list(source.records())
            history = list(source.records(kind="deregistered"))
        self.assertEqual(current[0]["record_kind"], "current")
        self.assertEqual(history[0]["record_kind"], "deregistered")
        self.assertEqual(history[0]["aircraft_reference"], {})
        self.assertEqual(history[0]["master"]["CANCEL DATE"], "20200101")

    def test_import_has_no_heavy_dependency_or_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with RegistryArchive(archive()) as source:
                self.assertEqual(len(list(source.records())), 1)
        for name in ("django", "pandas", "pyarrow", "duckdb"):
            self.assertNotIn(name, sys.modules)

    def test_malformed_row_does_not_silently_truncate(self):
        with RegistryArchive(archive("N-NUMBER,SERIAL NUMBER,MFR MDL CODE,NAME\n123AB,S,A,X,EXTRA\n")) as source:
            with self.assertRaises(ValueError):
                list(source.records())

if __name__ == "__main__":
    unittest.main()
