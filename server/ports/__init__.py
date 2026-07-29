"""应用层持久化端口。"""

from .repositories import (
    BackupPolicy,
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryError,
    RepositoryNotFound,
    RepositoryRecoveryRequired,
    RepositoryUnavailable,
    SettingsDocument,
    SettingsRepository,
    SongRepository,
    StoredSnapshot,
)

__all__ = [
    "BackupPolicy",
    "RepositoryClosed",
    "RepositoryConflict",
    "RepositoryCorrupt",
    "RepositoryError",
    "RepositoryNotFound",
    "RepositoryRecoveryRequired",
    "RepositoryUnavailable",
    "SettingsDocument",
    "SettingsRepository",
    "SongRepository",
    "StoredSnapshot",
]
