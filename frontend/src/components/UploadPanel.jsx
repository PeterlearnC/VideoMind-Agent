import { useRef, useState } from "react";

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

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m7 7 10 10M17 7 7 17" />
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

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function UploadPanel({
  file,
  busy,
  status,
  uploadProgress,
  errorMessage,
  onSelectFile,
  onClearFile,
  onSubmit,
}) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  return (
    <form className="upload-panel" onSubmit={onSubmit}>
      <div className="panel-heading">
        <div>
          <span className="section-number">01</span>
          <h2>选择视频</h2>
        </div>
        <span className="file-rule">MP4 · 最大 2 GB</span>
      </div>

      {!file ? (
        <button
          className={`dropzone ${dragging ? "is-dragging" : ""}`}
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
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            onSelectFile(event.dataTransfer.files?.[0]);
          }}
        >
          <span className="upload-icon"><UploadIcon /></span>
          <span className="dropzone-title">拖放视频到这里</span>
          <span className="dropzone-copy">或点击浏览本地文件</span>
          <span className="browse-label">选择 MP4</span>
        </button>
      ) : (
        <div className="selected-file">
          <span className="file-icon"><FilmIcon /></span>
          <span className="file-information">
            <strong>{file.name}</strong>
            <span>{formatFileSize(file.size)} · MP4 video</span>
          </span>
          <button
            className="remove-file"
            type="button"
            onClick={onClearFile}
            disabled={busy}
            aria-label="移除视频"
          >
            <CloseIcon />
          </button>
          {busy && (
            <span
              className="upload-progress"
              style={{ "--progress": `${uploadProgress}%` }}
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
          onSelectFile(event.target.files?.[0]);
          event.target.value = "";
        }}
      />

      <button className="generate-button" type="submit" disabled={!file || busy}>
        <span>
          {status === "uploading"
            ? `正在上传 ${uploadProgress}%`
            : status === "processing"
              ? "正在生成双语字幕"
              : "开始生成字幕"}
        </span>
        {busy ? <span className="button-spinner" aria-hidden="true" /> : <ArrowIcon />}
      </button>

      {status === "error" && (
        <div className="error-message" role="alert">
          <span aria-hidden="true">!</span>
          <p>{errorMessage}</p>
        </div>
      )}
    </form>
  );
}
