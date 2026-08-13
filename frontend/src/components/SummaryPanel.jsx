import { useEffect, useState } from "react";

function formatTimestamp(seconds) {
  const safeSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const remainder = safeSeconds % 60;
  return [hours, minutes, remainder]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

export default function SummaryPanel({
  videoId,
  currentTime = 0,
  onSeekToTime,
  outputLanguage = "zh",
  subtitleRevision = 0,
  workspaceRestored = false,
}) {
  const [status, setStatus] = useState("idle");
  const [summary, setSummary] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [generatedRevision, setGeneratedRevision] = useState(0);

  useEffect(() => {
    setStatus("idle");
    setSummary(null);
    setErrorMessage("");
    setGeneratedRevision(0);
  }, [videoId]);

  useEffect(() => {
    if (subtitleRevision === 0) setGeneratedRevision(0);
  }, [subtitleRevision]);

  async function generateSummary() {
    if (!videoId || status === "loading") return;
    setStatus("loading");
    setErrorMessage("");

    try {
      const response = await fetch(`/api/summary/${encodeURIComponent(videoId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output_language: outputLanguage }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail || "视频摘要生成失败。");
      }
      setSummary(payload);
      setGeneratedRevision(subtitleRevision);
      setStatus("success");
    } catch (error) {
      setStatus("error");
      setErrorMessage(error.message || "视频摘要生成失败，请稍后重试。");
    }
  }

  if (!videoId) return null;

  return (
    <section className="summary-panel" aria-labelledby="summary-title">
      <div className="summary-heading">
        <div>
          <span className="section-number">05</span>
          <div>
            <span className="summary-kicker">DeepSeek Video Agent</span>
            <h2 id="summary-title">AI 视频摘要</h2>
          </div>
        </div>
        <button
          className="summary-generate"
          type="button"
          disabled={status === "loading"}
          onClick={generateSummary}
        >
          {status === "loading" ? "Agent 分析中…" : summary ? "重新生成" : "生成摘要"}
        </button>
      </div>

      {subtitleRevision > generatedRevision && (
        <p className="linked-content-notice">字幕已修改，重新生成摘要后将使用最新人工字幕。</p>
      )}

      {status === "idle" && (
        <p className="summary-placeholder">
          {workspaceRestored
            ? "字幕工作区已恢复，可重新生成摘要。"
            : "Agent 将读取时间轴字幕，提炼视频概述、核心观点与章节结构。"}
        </p>
      )}
      {status === "loading" && (
        <div className="summary-loading" role="status">
          <span className="button-spinner" aria-hidden="true" />
          正在理解完整视频内容并组织摘要…
        </div>
      )}
      {status === "error" && (
        <div className="error-message summary-error" role="alert">
          <span aria-hidden="true">!</span>
          <p>{errorMessage}</p>
        </div>
      )}
      {summary && status === "success" && (
        <article className="summary-result">
          <header>
            <h3>{summary.title}</h3>
            <p>{summary.overview}</p>
          </header>
          <div className="summary-columns">
            <section>
              <h4>核心要点</h4>
              <ul>
                {summary.key_points.map((point, index) => (
                  <li key={`${index}-${point}`}>{point}</li>
                ))}
              </ul>
            </section>
            <section>
              <h4>内容章节</h4>
              <ol className="summary-chapters">
                {summary.chapters.map((chapter, index) => {
                  const start = Number(chapter.start) || 0;
                  const nextStart = Number(summary.chapters[index + 1]?.start);
                  const isCurrent =
                    currentTime >= start &&
                    (!Number.isFinite(nextStart) || currentTime < nextStart);

                  return (
                    <li
                      className={isCurrent ? "is-current" : undefined}
                      key={`${index}-${start}`}
                    >
                      <button
                        className="chapter-timestamp"
                        type="button"
                        onClick={() => onSeekToTime?.(start)}
                        aria-label={`跳转到 ${chapter.timestamp || formatTimestamp(start)}：${chapter.title}`}
                        aria-current={isCurrent ? "true" : undefined}
                      >
                        <time>{chapter.timestamp || formatTimestamp(start)}</time>
                      </button>
                      <div>
                        <strong>{chapter.title}</strong>
                        <p>{chapter.summary}</p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </section>
          </div>
          {summary.keywords.length > 0 && (
            <div className="summary-keywords" aria-label="关键词">
              {summary.keywords.map((keyword) => <span key={keyword}>{keyword}</span>)}
            </div>
          )}
        </article>
      )}
    </section>
  );
}
