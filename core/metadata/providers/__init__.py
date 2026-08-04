"""M2.8+ 在线元数据 Provider 集合。

按 M2.7 MetadataProvider 协议实现的各家在线音乐服务 provider。
M2.8 收口 NeteaseProvider；后续 M2.10+ 加 QQProvider / KugouProvider。

本包不 import UI/服务框架（与 core/ 铁律一致）。
"""
from .netease import NeteaseProvider

__all__ = ["NeteaseProvider"]
