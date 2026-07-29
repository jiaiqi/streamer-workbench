"""本地文件 Repository adapters。"""

from .atomic_json import AtomicJsonWriter, FaultInjector, MISSING_REVISION, json_revision
from .events import EventFaultInjector, FileEventStore
from .settings import FileSettingsRepository
from .songs import FileSongRepository

__all__ = [
    "AtomicJsonWriter",
    "FaultInjector",
    "EventFaultInjector",
    "FileEventStore",
    "FileSettingsRepository",
    "FileSongRepository",
    "MISSING_REVISION",
    "json_revision",
]
