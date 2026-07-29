"""本地文件 Repository adapters。"""

from .atomic_json import AtomicJsonWriter, FaultInjector, MISSING_REVISION, json_revision

__all__ = ["AtomicJsonWriter", "FaultInjector", "MISSING_REVISION", "json_revision"]
