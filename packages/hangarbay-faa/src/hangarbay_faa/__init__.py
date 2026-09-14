"""FAA source parsing without a database, framework, or import-time network."""
from .registry import RegistryArchive, download_archive, iter_aircraft, load_reference, member_name, read_rows

__version__ = "0.1.0"
__all__ = ["RegistryArchive", "download_archive", "iter_aircraft", "load_reference", "member_name", "read_rows"]
