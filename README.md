# VideoMind-Agent

VideoMind-Agent 是一个 AI 视频理解 Agent 工程框架。本阶段仅包含项目骨架与 FastAPI 服务入口，暂未实现业务功能。

## 项目结构

- `backend/`：FastAPI 后端服务
- `frontend/`：前端应用
- `agent/`：Agent、提示词和工具
- `data/`：视频、音频和字幕数据目录
- `docs/`：项目文档

## 启动后端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.app.main:app --reload
```

服务启动后可访问：

- 健康检查：`http://127.0.0.1:8000/health`
- API 文档：`http://127.0.0.1:8000/docs`
