import { useEffect, useRef, useState } from "react";

import UploadPanel from "./components/UploadPanel";
import VideoPlayer from "./components/VideoPlayer";
import SummaryPanel from "./components/SummaryPanel";

const API_ENDPOINT = "/api/generate-bilingual-subtitle";
const DOWNLOAD_ENDPOINT = "/downloads/bilingual.srt";
const MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024;

const PROCESS_STEPS = [
  { title: "上传视频", detail: "安全传输 MP4 文件" },
  { title: "语音识别", detail: "Whisper 检测语言与时间轴" },
  { title: "双语翻译", detail: "生成自然的中文字幕" },
  { title: "导出字幕", detail: "写入标准 SRT 文件" },
];

function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 4v11m0 0 4-4m-4 4-4-4M5 19.5h14" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h14m0 0-5-5m5 5-5 5" />
    </svg>
  );
}

function parseResponse(xhr) {
  let payload;
  try {
    payload = JSON.parse(xhr.responseText);
  } catch {
    payload = null;
  }

  if (xhr.status >= 200 && xhr.status < 300) {
    return payload;
  }

  const detail =
    typeof payload?.detail === "string"
      ? payload.detail
      : "请求失败（HTTP " + (xhr.status || "未知") + "）";
  throw new Error(detail);
}

function requestBilingualSubtitle(file, callbacks) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.open("POST", API_ENDPOINT);
    xhr.timeout = 30 * 60 * 1000;

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        callbacks.onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });
    xhr.upload.addEventListener("load", callbacks.onUploadComplete);
    xhr.addEventListener("load", () => {
      try {
        resolve(parseResponse(xhr));
      } catch (error) {
        reject(error);
      }
    });
    xhr.addEventListener("error", () => {
      reject(new Error("无法连接后端服务，请确认 FastAPI 已在 8000 端口运行。"));
    });
    xhr.addEventListener("timeout", () => {
      reject(new Error("处理超时，请检查视频长度或后端服务状态。"));
    });

    xhr.send(formData);
  });
}

function StatusTimeline({ status, uploadProgress }) {
  const isFinished = status === "success";
  const isProcessing = status === "processing";

  return (
    <ol className="status-timeline" aria-label="处理进度">
      {PROCESS_STEPS.map((step, index) => {
        let state = "pending";
        if (isFinished) {
          state = "complete";
        } else if (status === "uploading" && index === 0) {
          state = "active";
        } else if (isProcessing && index === 0) {
          state = "complete";
        } else if (isProcessing && index > 0) {
          state = "active";
        }

        return (
          <li
            className={"timeline-item timeline-" + state}
            key={step.title}
          >
            <span className="timeline-marker" aria-hidden="true">
              {state === "complete" ? "✓" : String(index + 1).padStart(2, "0")}
            </span>
            <span className="timeline-copy">
              <span className="timeline-title">
                {step.title}
                {status === "uploading" && index === 0
                  ? " · " + uploadProgress + "%"
                  : ""}
              </span>
              <span className="timeline-detail">{step.detail}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export default function App() {
  const [file, setFile] = useState(null);
  const [videoUrl, setVideoUrl] = useState("");
  const [subtitles, setSubtitles] = useState([]);
  const [videoId, setVideoId] = useState("");
  const [status, setStatus] = useState("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [seekRequest, setSeekRequest] = useState(null);
  const [playerCurrentTime, setPlayerCurrentTime] = useState(0);
  const playerRegionRef = useRef(null);

  const busy = status === "uploading" || status === "processing";

  function handleSeekToTime(startSeconds) {
    const targetTime = Number(startSeconds);
    if (!Number.isFinite(targetTime) || targetTime < 0) return;

    setSeekRequest({ targetTime, requestedAt: Date.now() });
    playerRegionRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  useEffect(() => {
    if (!file) {
      setVideoUrl("");
      return undefined;
    }

    const objectUrl = URL.createObjectURL(file);
    setVideoUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  function selectFile(candidate) {
    if (!candidate || busy) {
      return;
    }

    const isMp4 =
      candidate.type === "video/mp4" ||
      candidate.name.toLowerCase().endsWith(".mp4");

    if (!isMp4) {
      setFile(null);
      setResult(null);
      setSubtitles([]);
      setVideoId("");
      setStatus("error");
      setErrorMessage("请选择 MP4 格式的视频文件。");
      return;
    }

    if (candidate.size > MAX_FILE_SIZE) {
      setFile(null);
      setResult(null);
      setSubtitles([]);
      setVideoId("");
      setStatus("error");
      setErrorMessage("视频超过 2 GB，请选择更小的 MP4 文件。");
      return;
    }

    setFile(candidate);
    setResult(null);
    setSubtitles([]);
    setVideoId("");
    setStatus("idle");
    setUploadProgress(0);
    setErrorMessage("");
  }

  function clearFile() {
    if (busy) {
      return;
    }
    setFile(null);
    setResult(null);
    setSubtitles([]);
    setVideoId("");
    setStatus("idle");
    setUploadProgress(0);
    setErrorMessage("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!file || busy) {
      return;
    }

    setStatus("uploading");
    setUploadProgress(0);
    setResult(null);
    setErrorMessage("");

    try {
      const response = await requestBilingualSubtitle(file, {
        onProgress: setUploadProgress,
        onUploadComplete: () => {
          setUploadProgress(100);
          setStatus("processing");
        },
      });
      const videoId = response.subtitle_file
        .split("/")
        .pop()
        .replace(/\.srt$/i, "");
      const subtitleResponse = await fetch(
        `/api/subtitle/${encodeURIComponent(videoId)}`,
        { cache: "no-store" },
      );
      if (!subtitleResponse.ok) {
        const payload = await subtitleResponse.json().catch(() => null);
        throw new Error(payload?.detail || "无法加载生成的字幕。");
      }
      const subtitlePayload = await subtitleResponse.json();
      setSubtitles(subtitlePayload.subtitles || []);
      setVideoId(videoId);
      setResult({
        ...response,
        downloadUrl: DOWNLOAD_ENDPOINT + "?generated=" + Date.now(),
      });
      setStatus("success");
    } catch (error) {
      setStatus("error");
      setErrorMessage(error.message || "字幕生成失败，请稍后重试。");
    }
  }

  return (
    <main className="app-shell">
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />

      <header className="site-header">
        <a className="brand" href="/" aria-label="VideoMind Agent 首页">
          <span className="brand-mark">
            <span />
            <span />
            <span />
          </span>
          <span>VideoMind</span>
        </a>
        <span className="header-label">AI video understanding studio</span>
        <span className="service-indicator">
          <span aria-hidden="true" />
          Local workflow
        </span>
      </header>

      <section className="hero">
        <div className="eyebrow">
          <span>Whisper</span>
          <ArrowIcon />
          <span>DeepSeek</span>
          <ArrowIcon />
          <span>Summary</span>
        </div>
        <h1>
          一段视频，
          <br />
          <em>两种语言。</em>
        </h1>
        <p className="hero-copy">
          上传英文 MP4，自动识别语音、生成时间轴并翻译为中文，
          同步生成可直接使用的双语字幕，并由 AI Agent 提炼结构化视频摘要。
        </p>
      </section>

      <section className="workspace" aria-label="字幕生成工作区">
        <UploadPanel
          file={file}
          busy={busy}
          status={status}
          uploadProgress={uploadProgress}
          errorMessage={errorMessage}
          onSelectFile={selectFile}
          onClearFile={clearFile}
          onSubmit={handleSubmit}
        />

        <aside className="process-panel">
          <div className="panel-heading">
            <div>
              <span className="section-number">02</span>
              <h2>处理进度</h2>
            </div>
            <span className={"status-pill status-" + status}>
              {status === "idle" && "等待开始"}
              {status === "uploading" && "正在上传"}
              {status === "processing" && "AI 处理中"}
              {status === "success" && "生成完成"}
              {status === "error" && "需要重试"}
            </span>
          </div>

          <StatusTimeline status={status} uploadProgress={uploadProgress} />

          {status === "success" && result ? (
            <div className="result-card">
              <div className="result-topline">
                <span className="success-check" aria-hidden="true">
                  ✓
                </span>
                <div>
                  <strong>字幕已准备好</strong>
                  <span>{result.filename}</span>
                </div>
              </div>
              <div className="result-meta">
                <span>
                  检测语言 <strong>{result.language?.toUpperCase()}</strong>
                </span>
                <span>
                  输出文件 <strong>bilingual.srt</strong>
                </span>
              </div>
              <a
                className="download-button"
                href={result.downloadUrl}
                download="bilingual.srt"
              >
                <DownloadIcon />
                下载 bilingual.srt
              </a>
            </div>
          ) : (
            <div className="process-note">
              <span className="note-line" aria-hidden="true" />
              <p>
                {status === "processing"
                  ? "Whisper 正在分析语音，随后将由翻译服务生成中文字幕。请保持页面开启。"
                  : "处理时间取决于视频长度和本机性能。字幕会保留 Whisper 生成的精确时间轴。"}
              </p>
            </div>
          )}
        </aside>
      </section>

      <div ref={playerRegionRef} className="player-scroll-target">
        <VideoPlayer
          src={videoUrl}
          subtitles={subtitles}
          title={file ? file.name : "视频预览"}
          seekRequest={seekRequest}
          onTimeChange={setPlayerCurrentTime}
        />
      </div>

      <SummaryPanel
        videoId={videoId}
        currentTime={playerCurrentTime}
        onSeekToTime={handleSeekToTime}
      />

      <footer>
        <span>VideoMind Agent</span>
        <p>视频仅发送到你配置的本地后端服务。</p>
        <span>EN / 中文</span>
      </footer>
    </main>
  );
}
