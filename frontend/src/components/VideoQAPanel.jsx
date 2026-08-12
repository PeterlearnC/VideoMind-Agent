import { useEffect, useState } from "react";

export default function VideoQAPanel({ videoId, onSeekToTime }) {
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    setQuestion("");
    setStatus("idle");
    setResult(null);
    setErrorMessage("");
  }, [videoId]);

  async function submitQuestion(event) {
    event.preventDefault();
    const normalizedQuestion = question.trim();
    if (!videoId || !normalizedQuestion || status === "loading") return;

    setStatus("loading");
    setErrorMessage("");

    try {
      const response = await fetch(`/api/qa/${encodeURIComponent(videoId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: normalizedQuestion }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail || "视频问答请求失败。");
      }
      setResult(payload);
      setStatus("success");
    } catch (error) {
      setStatus("error");
      setErrorMessage(error.message || "视频问答失败，请稍后重试。");
    }
  }

  if (!videoId) return null;

  return (
    <section className="qa-panel" aria-labelledby="qa-title">
      <div className="qa-heading">
        <div>
          <span className="section-number">05</span>
          <div>
            <span className="summary-kicker">Grounded Video Q&amp;A</span>
            <h2 id="qa-title">AI 视频问答</h2>
          </div>
        </div>
      </div>

      <form className="qa-form" onSubmit={submitQuestion}>
        <label htmlFor="video-question">基于当前视频字幕提问</label>
        <div className="qa-input-row">
          <input
            id="video-question"
            type="text"
            value={question}
            maxLength={1000}
            placeholder="例如：这个视频什么时候介绍了刹车系统？"
            disabled={status === "loading"}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button
            type="submit"
            disabled={!question.trim() || status === "loading"}
          >
            {status === "loading" ? "回答中…" : "发送问题"}
          </button>
        </div>
      </form>

      {status === "loading" && (
        <div className="qa-loading" role="status">
          <span className="button-spinner" aria-hidden="true" />
          Agent 正在定位相关字幕并组织回答…
        </div>
      )}
      {status === "error" && (
        <div className="error-message qa-error" role="alert">
          <span aria-hidden="true">!</span>
          <p>{errorMessage}</p>
        </div>
      )}
      {result && status === "success" && (
        <article className="qa-result" aria-live="polite">
          <div className="qa-answer">
            <h3>AI 回答</h3>
            <p>{result.answer}</p>
          </div>
          {result.references.length > 0 && (
            <div className="qa-references">
              <h3>相关视频片段</h3>
              <ol>
                {result.references.map((reference, index) => (
                  <li key={`${index}-${reference.start}`}>
                    <button
                      type="button"
                      onClick={() => onSeekToTime?.(reference.start)}
                      aria-label={`跳转到 ${reference.timestamp}`}
                    >
                      <time>{reference.timestamp}</time>
                    </button>
                    <p>{reference.text}</p>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </article>
      )}
    </section>
  );
}
