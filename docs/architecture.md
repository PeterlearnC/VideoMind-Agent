# VideoMind-Agent Architecture

## System Overview

VideoMind-Agent is an AI-powered video understanding system,
including video processing, bilingual subtitle generation and AI summary.


```mermaid
graph TD

A[User Upload Video]

A --> B[React Frontend]

B --> C[FastAPI Backend]


C --> D[Whisper ASR]

D --> E[Timestamp Subtitle Generation]

E --> F[Bilingual Subtitle Player]


D --> G[DeepSeek Video Agent]

G --> H[Structured Video Summary]


H --> I[Summary Panel]

I --> J[Key Points]
I --> K[Timeline Chapters]
I --> L[Keywords]

```

## Module Description

### Frontend

Technology:

- React
- Vite
- HTML5 Video Player

Functions:

- Video upload
- Subtitle rendering
- Real-time subtitle switching
- AI summary display


### Backend

Technology:

- FastAPI
- Python


Functions:

- Video processing API
- Subtitle generation
- DeepSeek Agent service
- Summary API


### AI Pipeline


Video

↓

Whisper Speech Recognition

↓

Subtitle Alignment

↓

DeepSeek Video Understanding

↓

Structured Summary

