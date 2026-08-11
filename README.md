# 🎬 VideoMind-Agent

## AI 视频理解智能体 | AI Video Understanding Agent

VideoMind-Agent 是一个基于人工智能的视频理解系统。

项目集成：

- Whisper 语音识别模型
- 中英双语字幕生成
- DeepSeek 视频理解智能体
- 结构化视频摘要生成


---

# ✨ 项目演示


## 视频上传



## 实时双语字幕



## AI 视频摘要



---

# 🚀 核心功能


## 1. AI 字幕生成

- 自动语音识别
- 时间轴精准对齐
- 英文-中文双语字幕生成


## 2. 智能视频播放器

- 基于 HTML5 的视频播放
- 字幕实时同步显示
- 字幕语言切换


## 3. AI 视频摘要智能体

基于 DeepSeek：

- 视频内容概览
- 核心要点提取
- 时间线章节划分
- 关键词生成


---

# 🏗 系统架构


系统流程：

```
视频上传

↓

Whisper 语音识别

↓

字幕时间轴对齐

↓

DeepSeek 智能体分析

↓

结构化摘要生成

↓

用户交互界面
```


---

# 🛠 技术栈


## 前端

- React
- Vite
- JavaScript
- HTML5 Video


## 后端

- FastAPI
- Python


## AI 模型

- Whisper
- DeepSeek API



---

# 📦 安装部署


## 1. 克隆项目


```bash
git clone https://github.com/PeterlearnC/VideoMind-Agent.git

cd VideoMind-Agent
```


---

# 后端部署


进入后端目录：

```bash
cd backend
```


创建 Python 虚拟环境：

```bash
python -m venv venv
```


激活虚拟环境：

```bash
venv\Scripts\activate
```


安装依赖：

```bash
pip install -r requirements.txt
```


启动后端服务：

```bash
uvicorn app.main:app --reload --port 8000
```


---

# 前端部署


进入前端目录：

```bash
cd frontend
```


安装依赖：

```bash
npm install
```


启动前端：

```bash
npm run dev
```


浏览器访问：

```
http://127.0.0.1:5174
```


---

# 🔑 环境变量配置


创建配置文件：

```
.env
```


添加 DeepSeek API Key：

```
DEEPSEEK_API_KEY=your_api_key_here
```


⚠️ 请勿将真实 API Key 上传至 GitHub。


---

# 📚 API 接口


## 双语字幕生成


```
POST /generate-bilingual-subtitle
```


## 获取字幕


```
GET /subtitle/bilingual
```


## 生成视频摘要


```
POST /summary/{video_id}
```



---

# 🗺 开发路线


## V0.1

✅ 视频上传

✅ Whisper 字幕生成


## V0.2

✅ 双语字幕播放器

✅ 字幕控制面板


## V0.3

✅ DeepSeek 视频摘要智能体

✅ 结构化摘要展示面板

✅ 项目文档完善


## 后续规划

- 多智能体视频分析
- 长视频记忆能力
- 知识库集成
- 在线部署


---

# 📄 开源协议

MIT License