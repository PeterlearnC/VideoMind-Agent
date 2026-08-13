import { useEffect, useRef, useState } from "react";

export default function VideoQAPanel({ videoId, onSeekToTime, subtitleRevision = 0, workspaceRestored = false }) {
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState("idle");
  const [history, setHistory] = useState([]);
  const [errorMessage, setErrorMessage] = useState("");
  const activeVideoIdRef = useRef(videoId);
  const requestVersionRef = useRef(0);
  const nextTurnIdRef = useRef(1);

  activeVideoIdRef.current = videoId;

  useEffect(() => {
    setQuestion("");
    setStatus("idle");
    setHistory([]);
    setErrorMessage("");
    requestVersionRef.current += 1;
    nextTurnIdRef.current = 1;
  }, [videoId]);

  function clearHistory() {
    setHistory([]);
    setStatus("idle");
    setErrorMessage("");
    requestVersionRef.current += 1;
    nextTurnIdRef.current = 1;
  }

  async function submitQuestion(event) {
    event.preventDefault();
    const normalizedQuestion = question.trim();
    if (!videoId || !normalizedQuestion || status === "loading") return;

    const requestedVideoId = videoId;
    const requestVersion = requestVersionRef.current;
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
      if (
        activeVideoIdRef.current !== requestedVideoId ||
        requestVersionRef.current !== requestVersion
      ) {
        return;
      }
      const turnId = nextTurnIdRef.current;
      nextTurnIdRef.current += 1;
      setHistory((previousHistory) => [
        ...previousHistory,
        {
          id: turnId,
          question: normalizedQuestion,
          answer: payload.answer,
          references: payload.references || [],
        },
      ]);
      setQuestion("");
      setStatus("success");
    } catch (error) {
      if (
        activeVideoIdRef.current !== requestedVideoId ||
        requestVersionRef.current !== requestVersion
      ) {
        return;
      }
      setStatus("error");
      setErrorMessage(error.message || "视频问答失败，请稍后重试。");
    }
  }

  if (!videoId) return null;

  return (
    <section className="qa-panel" aria-labelledby="qa-title">
      <div className="qa-heading">
        <div>
          <span className="section-number">06</span>
          <div>
            <span className="summary-kicker">Grounded Video Q&amp;A</span>
            <h2 id="qa-title">AI 视频问答</h2>
          </div>
        </div>
        {history.length > 0 && (
          <button className="qa-clear" type="button" onClick={clearHistory}>
            清空问答
          </button>
        )}
      </div>

      {workspaceRestored && (
        <p className="linked-content-notice">工作区已恢复，历史问答未持久化。</p>
      )}

      {subtitleRevision > 0 && (
        <p className="linked-content-notice">字幕已更新。之后的新问题将使用最新字幕内容，历史回答不会自动重算。</p>
      )}

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
      {history.length > 0 && (
        <div className="qa-history" aria-live="polite" aria-label="问答历史">
          {history.map((turn, turnIndex) => (
            <article className="qa-turn" key={turn.id}>
              <div className="qa-question">
                <span>问题 {String(turnIndex + 1).padStart(2, "0")}</span>
                <p>{turn.question}</p>
              </div>
              <div className="qa-result">
                <div className="qa-answer">
                  <h3>AI 回答</h3>
                  <p>{turn.answer}</p>
                </div>
                {turn.references.length > 0 && (
                  <div className="qa-references">
                    <h3>相关视频片段</h3>
                    <ol>
                      {turn.references.map((reference, index) => (
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
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
