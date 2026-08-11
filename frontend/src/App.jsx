import { useRef, useState } from "react";

const API_ENDPOINT = "/api/generate-bilingual-subtitle";
const DOWNLOAD_ENDPOINT = "/downloads/bilingual.srt";
const MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024;

const PROCESS_STEPS = [
  { title: "上传视频", detail: "安全传输 MP4 文件" },
  { title: "语音识别", detail: "Whisper 检测语言与时间轴" },
  { title: "双语翻译", detail: "生成自然的中文字幕" },
  { title: "导出字幕", detail: "写入标准 SRT 文件" },
];

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14.5v3.25A2.25 2.25 0 0 0 7.25 20h9.5A2.25 2.25 0 0 0 19 17.75V14.5" />
    </svg>
  );
}

function FilmIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
      <path d="M7 4.5v15M17 4.5v15M3 9h4m10 0h4M3 15h4m10 0h4" />
    </svg>
  );
}

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

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m7 7 10 10M17 7 7 17" />
    </svg>
  );
}

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) {
    return (bytes / 1024).toFixed(1) + " KB";
  }
  if (bytes < 1024 * 1024 * 1024) {
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + " GB";
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
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");

  const busy = status === "uploading" || status === "processing";

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
      setStatus("error");
      setErrorMessage("请选择 MP4 格式的视频文件。");
      return;
    }

    if (candidate.size > MAX_FILE_SIZE) {
      setFile(null);
      setResult(null);
      setStatus("error");
      setErrorMessage("视频超过 2 GB，请选择更小的 MP4 文件。");
      return;
    }

    setFile(candidate);
    setResult(null);
    setStatus("idle");
    setUploadProgress(0);
    setErrorMessage("");
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  function clearFile() {
    if (busy) {
      return;
    }
    setFile(null);
    setResult(null);
    setStatus("idle");
    setUploadProgress(0);
    setErrorMessage("");
    if (inputRef.current) {
      inputRef.current.value = "";
    }
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
        <span className="header-label">Bilingual subtitle studio</span>
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
          <span>SRT</span>
        </div>
        <h1>
          一段视频，
          <br />
          <em>两种语言。</em>
        </h1>
        <p className="hero-copy">
          上传英文 MP4，自动识别语音、生成时间轴并翻译为中文，
          一次导出可直接使用的中英双语字幕。
        </p>
      </section>

      <section className="workspace" aria-label="字幕生成工作区">
        <form className="upload-panel" onSubmit={handleSubmit}>
          <div className="panel-heading">
            <div>
              <span className="section-number">01</span>
              <h2>选择视频</h2>
            </div>
            <span className="file-rule">MP4 · 最大 2 GB</span>
          </div>

          {!file ? (
            <button
              className={"dropzone " + (dragging ? "is-dragging" : "")}
              type="button"
              disabled={busy}
              onClick={() => inputRef.current?.click()}
              onDragEnter={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) {
                  setDragging(false);
                }
              }}
              onDrop={handleDrop}
            >
              <span className="upload-icon">
                <UploadIcon />
              </span>
              <span className="dropzone-title">拖放视频到这里</span>
              <span className="dropzone-copy">或点击浏览本地文件</span>
              <span className="browse-label">选择 MP4</span>
            </button>
          ) : (
            <div className="selected-file">
              <span className="file-icon">
                <FilmIcon />
              </span>
              <span className="file-information">
                <strong>{file.name}</strong>
                <span>{formatFileSize(file.size)} · MP4 video</span>
              </span>
              <button
                className="remove-file"
                type="button"
                onClick={clearFile}
                disabled={busy}
                aria-label="移除视频"
              >
                <CloseIcon />
              </button>
              {busy && (
                <span
                  className="upload-progress"
                  style={{ "--progress": uploadProgress + "%" }}
                  aria-hidden="true"
                />
              )}
            </div>
          )}

          <input
            ref={inputRef}
            className="visually-hidden"
            type="file"
            accept="video/mp4,.mp4"
            onChange={(event) => {
              selectFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />

          <button
            className="generate-button"
            type="submit"
            disabled={!file || busy}
          >
            <span>
              {status === "uploading"
                ? "正在上传 " + uploadProgress + "%"
                : status === "processing"
                  ? "正在生成双语字幕"
                  : "开始生成字幕"}
            </span>
            {busy ? (
              <span className="button-spinner" aria-hidden="true" />
            ) : (
              <ArrowIcon />
            )}
          </button>

          {status === "error" && (
            <div className="error-message" role="alert">
              <span aria-hidden="true">!</span>
              <p>{errorMessage}</p>
            </div>
          )}
        </form>

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

      <footer>
        <span>VideoMind Agent</span>
        <p>视频仅发送到你配置的本地后端服务。</p>
        <span>EN / 中文</span>
      </footer>
    </main>
  );
}