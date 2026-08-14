# VideoMind-Agent v0.7.4 Competition Demo

AI 视频理解与双语字幕智能工作台（Competition Demo / Prototype）。

## 30 秒快速开始

1. 将 ZIP 完整解压到一个可写目录。
2. 首次运行双击 `prepare_videomind_demo.bat`。它只会在缺少配置时创建安全的 `backend/.env`，不会写入 API Key。
3. 如依赖尚未安装，可双击 `install_dependencies.bat`；它只安装项目 Python/npm 依赖，不安装系统软件。
4. 双击 `start_videomind.bat`，等待 Backend、Frontend 就绪并自动打开浏览器。
5. 体验双语字幕、播放同步、Subtitle Editor、AI Video Summary、Grounded Video Q&A、时间戳跳转、自定义字幕和全屏字幕。
6. 体验结束后双击 `stop_videomind.bat`。

## 两种运行模式

### Mode A · Competition Demo Mode

无需 DeepSeek API Key。页面会明确显示 **Preloaded Demo / Competition Demo**，可浏览预置的项目自有测试视频、双语字幕、Summary、Grounded Q&A，并体验 Player、Editor、SRT Export 与 Timestamp Seek。

预置 Summary/Q&A 来自仓库已有自动化测试 fixture，并非启动后实时调用 AI。没有 API Key 时，处理新视频、重新生成 Correction/Translation/Summary 或发起新 Q&A 会收到清晰的 Demo Mode 提示，不会伪装为实时 AI。

### Mode B · Full AI Mode

在 `backend/.env` 中自行配置：

```dotenv
COMPETITION_DEMO_MODE=false
DEEPSEEK_API_KEY=your_api_key_here
```

配置当前项目所需 Whisper 环境后，可以上传新视频并使用 Transcript Correction、Translation、Summary 和 Q&A。密钥仅由使用者自己提供；发行包不包含任何 API Key。

当前稳定环境使用 `openai-whisper==20250625`。Full AI Mode 可在完成基础依赖安装后执行：

```powershell
backend\venv\Scripts\python.exe -m pip install openai-whisper==20250625
```

首次运行 Whisper 时还可能下载所选模型文件；Competition Demo Mode 不需要该步骤。

## 首次运行前提

- Windows 10 / 11
- Python 3.11
- Node.js 与 npm
- PATH 中可用的 FFmpeg 与 ffprobe
- Backend/Frontend dependencies（可运行 `install_dependencies.bat`）
- Full AI Mode 还需要当前项目的 Whisper 模型环境与使用者自己的 DeepSeek API Key

本发行包是源码形式的 Competition Demo，不是自包含 EXE，也不会自动安装 Python、Node.js 或 FFmpeg，不会修改 PATH、注册表或系统级设置。

## Troubleshooting

- 浏览器未自动打开：访问 <http://127.0.0.1:5173>
- Backend health：<http://127.0.0.1:8000/health>
- 端口冲突：先运行 `stop_videomind.bat`；脚本不会终止未知进程
- Python not found：安装 Python 3.11，或创建 `backend/venv`
- Node/npm not found：安装 Node.js 后运行 `install_dependencies.bat`
- FFmpeg/ffprobe not found：安装并加入 PATH
- DeepSeek API Key missing：Competition Demo Mode 仍可浏览预置结果，只有实时 Cloud AI 功能不可用

启动失败时请保留 Backend/Frontend 命令窗口，并根据其中的错误信息检查依赖。
