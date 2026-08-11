# VideoMind-Agent

VideoMind-Agent 是一个 AI 视频理解应用。V0.3.0 支持 Whisper 视频转写、DeepSeek
双语字幕、实时字幕播放器，以及基于时间轴字幕的结构化 AI 视频摘要。

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

## V0.3.0 主要接口

- `POST /generate-bilingual-subtitle`：生成中英双语字幕
- `GET /subtitle/{video_id}`：读取时间轴字幕 JSON
- `POST /summary/{video_id}`：生成标题、概述、要点、章节和关键词

DeepSeek 功能需要在 `backend/.env` 或运行环境中配置 `DEEPSEEK_API_KEY`。
