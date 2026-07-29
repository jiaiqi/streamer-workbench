"""不依赖 Web 框架的 API 错误契约与 Repository 错误映射。"""

from dataclasses import asdict, dataclass, field
from typing import Any

from server.ports.repositories import (
    RepositoryClosed,
    RepositoryConflict,
    RepositoryCorrupt,
    RepositoryNotFound,
    RepositoryRecoveryRequired,
    RepositoryUnavailable,
)


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    recovery: str | None = None
    request_id: str | None = None

    def envelope(self) -> dict[str, Any]:
        return {
            "error": {
                key: value
                for key, value in asdict(self).items()
                if value is not None
            }
        }


def map_repository_error(error: Exception) -> tuple[int, ApiError]:
    mappings = (
        (RepositoryNotFound, 404, "repository_not_found", "请求的数据不存在", "刷新后重试"),
        (RepositoryConflict, 409, "repository_conflict", "数据已被其他操作修改", "重新加载后再提交"),
        (RepositoryCorrupt, 500, "repository_corrupt", "本地数据损坏", "从备份恢复或查看诊断"),
        (RepositoryRecoveryRequired, 503, "repository_recovery_required", "本地数据需要恢复", "完成恢复后重试"),
        (RepositoryClosed, 503, "repository_closed", "本地数据服务已关闭", "重启应用后重试"),
        (RepositoryUnavailable, 503, "repository_unavailable", "本地数据暂时不可用", "稍后重试"),
    )
    for kind, status, code, message, recovery in mappings:
        if isinstance(error, kind):
            return status, ApiError(
                code,
                message,
                details={"reason": str(error)} if str(error) else {},
                recovery=recovery,
            )
    return 500, ApiError(
        "internal_error",
        "内部错误",
        recovery="重试；若持续失败请查看日志",
    )
