"""PyInstaller 打包 spike：后端单文件可执行入口。

用法（项目根目录）：
    .venv/bin/pyinstaller --onefile --name poster-backend \
        --add-data "themes:themes" --add-data "fonts:fonts" --add-data "data:data" \
        --paths . packaging/backend_entry.py

结论记录（见 agent-handoff 文档 §10）：
- sys.frozen 时 server/main.py 的 __file__ 指向 _MEIPASS 临时解压目录，
  其 ROOT 推导自然命中 --add-data 打进来的 themes/fonts，只读资源可直接用。
- 可写数据（data/songs.json、settings.json、backups、output）绝不能用
  _MEIPASS：进程退出即销毁。正式打包必须把可写目录解析到用户目录
  （如 exe 同级的 ./poster-data 或 ~/Library/Application Support）。
"""
import os

import uvicorn

from server.main import app  # 显式导入：让 PyInstaller 静态分析打到 server 包及其依赖

if __name__ == "__main__":
    port = int(os.environ.get("GP_PORT", "8001"))  # spike 用 8001，避开开发后端 8000
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
