"""主播工作台本地后端兼容入口。

运行：python -m server --reload --port 8000
"""
import logging

from server.app import create_app
from server.config import AppConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

# 构造 app 不写盘；数据加载和目录初始化在 lifespan 启动阶段完成。
app = create_app(AppConfig.from_environment(mode="development"))
