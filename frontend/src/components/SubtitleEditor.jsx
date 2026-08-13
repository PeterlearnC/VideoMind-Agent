import { useEffect, useMemo, useRef, useState } from "react";

import {
  AUTO_SCROLL_RESUME_DELAY,
  activeCueId,
  internalScrollTarget,
  shouldAutoScroll,
} from "../subtitleAutoScroll.js";
import { findActiveCueId } from "../subtitleTiming.js";

function formatTimestamp(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remainder = (value % 60).toFixed(3).padStart(6, "0");
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${remainder}`;
}

function effectiveSource(cue) {
  return cue.edited_source_text ?? cue.corrected_text ?? cue.source_text ?? cue.source ?? "";
}

function effectiveTranslation(cue) {
  return cue.edited_translated_text ?? cue.translated_text ?? cue.translation ?? "";
}

function HighlightedText({ text, query }) {
  const needle = query.trim();
  if (!needle) return text || "无";
  const lower = String(text).toLocaleLowerCase();
  const normalizedNeedle = needle.toLocaleLowerCase();
  const parts = [];
  let cursor = 0;
  let matchIndex = lower.indexOf(normalizedNeedle);
  while (matchIndex !== -1) {
    parts.push(String(text).slice(cursor, matchIndex));
    parts.push(<mark key={`${matchIndex}-${cursor}`}>{String(text).slice(matchIndex, matchIndex + needle.length)}</mark>);
    cursor = matchIndex + needle.length;
    matchIndex = lower.indexOf(normalizedNeedle, cursor);
  }
  parts.push(String(text).slice(cursor));
  return parts;
}

export default function SubtitleEditor({
  videoId,
  currentTime = 0,
  onSeekToTime,
  onSubtitlesChange,
  onDirtyChange,
  onSaved,
  resetToken = 0,
  reloadToken = 0,
  sourceLanguage,
  targetLanguage,
}) {
  const [cues, setCues] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [cueStatuses, setCueStatuses] = useState({});
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState({});
  const editorRef = useRef(null);
  const listRef = useRef(null);
  const cueRefs = useRef({});
  const activeIdRef = useRef(null);
  const userScrollingRef = useRef(false);
  const editingRef = useRef(false);
  const resumeTimerRef = useRef(null);
  const programmaticScrollRef = useRef(false);

  const dirtyIds = Object.keys(drafts);
  const renderedActiveId = findActiveCueId(cues, currentTime);
  useEffect(() => onDirtyChange?.(dirtyIds.length), [dirtyIds.length, onDirtyChange]);

  useEffect(() => {
    setCues([]);
    setDrafts({});
    setCueStatuses({});
    setQuery("");
    setError("");
    if (!videoId) return;
    let cancelled = false;
    setStatus("loading");
    fetch(`/api/subtitle/editor/${encodeURIComponent(videoId)}`, { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json().catch(() => null);
        if (!response.ok) throw new Error(payload?.detail || "无法加载字幕编辑数据。");
        if (!cancelled) {
          setCues(payload.subtitles || []);
          setStatus("ready");
        }
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(requestError.message);
          setStatus("error");
        }
      });
    return () => { cancelled = true; };
  }, [videoId, reloadToken]);

  useEffect(() => {
    if (!resetToken) return;
    setDrafts({});
    setCueStatuses({});
  }, [resetToken]);

  useEffect(() => {
    const activeId = activeCueId(cues, currentTime);
    if (activeId && activeId !== activeIdRef.current) {
      activeIdRef.current = activeId;
      if (!shouldAutoScroll({
        userScrolling: userScrollingRef.current,
        editing: editingRef.current,
        query,
      })) return;
      const container = listRef.current;
      const target = internalScrollTarget(container, cueRefs.current[activeId]);
      if (target === null) return;
      programmaticScrollRef.current = true;
      container.scrollTo({ top: target, behavior: "smooth" });
      window.setTimeout(() => { programmaticScrollRef.current = false; }, 250);
    }
  }, [currentTime, cues, query]);

  useEffect(() => () => {
    if (resumeTimerRef.current) window.clearTimeout(resumeTimerRef.current);
  }, []);

  function pauseAutoScroll() {
    userScrollingRef.current = true;
    if (resumeTimerRef.current) window.clearTimeout(resumeTimerRef.current);
    resumeTimerRef.current = window.setTimeout(() => {
      userScrollingRef.current = false;
      resumeTimerRef.current = null;
    }, AUTO_SCROLL_RESUME_DELAY);
  }

  function pauseForEditing() {
    editingRef.current = true;
    pauseAutoScroll();
  }

  function resumeAfterEditing() {
    editingRef.current = false;
    pauseAutoScroll();
  }

  useEffect(() => {
    const pauseForPageInteraction = () => pauseAutoScroll();
    window.addEventListener("wheel", pauseForPageInteraction, { passive: true });
    window.addEventListener("touchmove", pauseForPageInteraction, { passive: true });
    window.addEventListener("pointerdown", pauseForPageInteraction, { passive: true });
    window.addEventListener("scroll", pauseForPageInteraction, { passive: true });
    return () => {
      window.removeEventListener("wheel", pauseForPageInteraction);
      window.removeEventListener("touchmove", pauseForPageInteraction);
      window.removeEventListener("pointerdown", pauseForPageInteraction);
      window.removeEventListener("scroll", pauseForPageInteraction);
    };
  }, []);

  useEffect(() => {
    const warn = (event) => {
      if (!dirtyIds.length) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirtyIds.length]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return cues;
    return cues.filter((cue) =>
      `${effectiveSource(cue)} ${effectiveTranslation(cue)}`.toLocaleLowerCase().includes(needle),
    );
  }, [cues, query]);

  const editedCount = cues.filter((cue) => cue.is_source_edited || cue.is_translation_edited).length;

  function draftFor(cue) {
    return {
      source_text: effectiveSource(cue),
      translated_text: effectiveTranslation(cue),
      ...(drafts[String(cue.id)] || {}),
    };
  }

  function changeDraft(cue, field, value) {
    const id = String(cue.id);
    const baseline = field === "source_text" ? effectiveSource(cue) : effectiveTranslation(cue);
    setDrafts((previous) => {
      const nextCue = { ...(previous[id] || {}) };
      if (value === baseline) delete nextCue[field];
      else nextCue[field] = value;
      const next = { ...previous };
      if (Object.keys(nextCue).length) next[id] = nextCue;
      else delete next[id];
      return next;
    });
    setCueStatuses((previous) => ({ ...previous, [id]: "dirty" }));
  }

  function mergeSaved(saved) {
    const byId = new Map(saved.map((cue) => [String(cue.id), cue]));
    setCues((previous) => {
      const next = previous.map((cue) => byId.get(String(cue.id)) || cue);
      onSubtitlesChange?.(next);
      return next;
    });
    setDrafts((previous) => {
      const next = { ...previous };
      saved.forEach((cue) => delete next[String(cue.id)]);
      return next;
    });
  }

  async function saveUpdates(updates) {
    if (!updates.length) return;
    const ids = updates.map((update) => String(update.id));
    setCueStatuses((previous) => ({
      ...previous,
      ...Object.fromEntries(ids.map((id) => [id, "saving"])),
    }));
    setError("");
    try {
      const response = await fetch(`/api/subtitle/editor/${encodeURIComponent(videoId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.detail || "字幕保存失败。");
      const saved = payload.subtitles || [];
      mergeSaved(saved);
      setCueStatuses((previous) => ({
        ...previous,
        ...Object.fromEntries(ids.map((id) => [id, "saved"])),
      }));
      onSaved?.(saved);
    } catch (requestError) {
      setError(requestError.message);
      setCueStatuses((previous) => ({
        ...previous,
        ...Object.fromEntries(ids.map((id) => [id, "error"])),
      }));
    }
  }

  function saveCue(cue) {
    const draft = drafts[String(cue.id)];
    if (draft) saveUpdates([{ id: cue.id, ...draft }]);
  }

  function saveAll() {
    saveUpdates(cues.filter((cue) => drafts[String(cue.id)]).map((cue) => ({
      id: cue.id,
      ...drafts[String(cue.id)],
    })));
  }

  async function resetCue(cue) {
    if (!window.confirm("重置后将恢复 AI 生成的原文和译文，是否继续？")) return;
    const id = String(cue.id);
    setCueStatuses((previous) => ({ ...previous, [id]: "saving" }));
    setError("");
    try {
      const response = await fetch(
        `/api/subtitle/editor/${encodeURIComponent(videoId)}/${encodeURIComponent(cue.id)}/reset`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ field: "all" }) },
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.detail || "字幕重置失败。");
      mergeSaved([payload]);
      setCueStatuses((previous) => ({ ...previous, [id]: "saved" }));
      onSaved?.([payload]);
    } catch (requestError) {
      setError(requestError.message);
      setCueStatuses((previous) => ({ ...previous, [id]: "error" }));
    }
  }

  function cueState(cue, id) {
    const requestState = cueStatuses[id];
    if (requestState === "saving") return ["saving", "保存中"];
    if (requestState === "error" && drafts[id]) return ["error", "保存失败"];
    if (drafts[id]) return ["dirty", "未保存"];
    if (cue.is_source_edited || cue.is_translation_edited) return ["saved", "已编辑"];
    return ["clean", "AI生成"];
  }

  if (!videoId) return null;
  const sameLanguage = sourceLanguage === targetLanguage;

  return (
    <section ref={editorRef} className="subtitle-editor" aria-labelledby="subtitle-editor-title" onWheel={pauseAutoScroll} onTouchMove={pauseAutoScroll} onPointerDown={pauseAutoScroll}>
      <div className="editor-heading">
        <div>
          <span className="section-number">04</span>
          <div><span className="summary-kicker">Human-in-the-loop</span><h2 id="subtitle-editor-title">字幕编辑</h2></div>
        </div>
        <div className="editor-actions">
          <label className="editor-search"><span className="visually-hidden">搜索字幕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索字幕…" /></label>
          <button type="button" disabled={!dirtyIds.length || Object.values(cueStatuses).includes("saving")} onClick={saveAll}>保存全部修改{dirtyIds.length ? ` (${dirtyIds.length})` : ""}</button>
          <a href={`/api/subtitle/${encodeURIComponent(videoId)}/export?v=${Date.now()}`} download={`${videoId}.srt`}>导出 SRT</a>
        </div>
      </div>
      <div className="editor-stats" aria-label="字幕编辑统计">
        <span>总字幕：<strong>{cues.length}</strong></span>
        <span>已人工编辑：<strong>{editedCount}</strong></span>
        <span>未保存：<strong>{dirtyIds.length}</strong></span>
        {query.trim() && <span>搜索：{query.trim()} · <strong>{filtered.length} 条结果</strong></span>}
      </div>
      {dirtyIds.length > 0 && <p className="editor-notice">你还有未保存的字幕修改。继续切换或重新生成将丢失这些内容。</p>}
      {error && <div className="error-message" role="alert"><span>!</span><p>{error}</p></div>}
      {status === "loading" ? <p className="editor-empty">正在加载字幕工作台…</p> : (
        <div ref={listRef} className="editor-list" onScroll={() => { if (!programmaticScrollRef.current) pauseAutoScroll(); }}>
          {filtered.map((cue) => {
            const id = String(cue.id);
            const draft = draftFor(cue);
            const dirty = Boolean(drafts[id]);
            const active = id === renderedActiveId;
            const [state, stateLabel] = cueState(cue, id);
            return (
              <article ref={(node) => { cueRefs.current[id] = node; }} className={`editor-cue${active ? " is-current" : ""}`} key={id}>
                <header>
                  <button type="button" className="editor-time" onClick={() => onSeekToTime?.(cue.start)}>{formatTimestamp(cue.start)} → {formatTimestamp(cue.end)}</button>
                  <span className={`editor-state is-${state}`}>{stateLabel}</span>
                </header>
                {query.trim() && <div className="editor-match-preview"><HighlightedText text={`${effectiveSource(cue)}${sameLanguage ? "" : ` / ${effectiveTranslation(cue)}`}`} query={query} /></div>}
                <label>原文<textarea maxLength={5000} disabled={state === "saving"} value={draft.source_text} onFocus={pauseForEditing} onBlur={resumeAfterEditing} onChange={(event) => changeDraft(cue, "source_text", event.target.value)} onKeyDown={(event) => { if (event.ctrlKey && event.key === "Enter") { event.preventDefault(); saveCue(cue); } }} /></label>
                {!sameLanguage && <label>译文<textarea maxLength={5000} disabled={state === "saving"} value={draft.translated_text} onFocus={pauseForEditing} onBlur={resumeAfterEditing} onChange={(event) => changeDraft(cue, "translated_text", event.target.value)} onKeyDown={(event) => { if (event.ctrlKey && event.key === "Enter") { event.preventDefault(); saveCue(cue); } }} /></label>}
                <div className="editor-cue-actions">
                  <button type="button" disabled={!dirty || state === "saving"} onClick={() => saveCue(cue)}>保存</button>
                  <button type="button" disabled={!dirty || state === "saving"} onClick={() => { setDrafts((previous) => { const next = { ...previous }; delete next[id]; return next; }); setCueStatuses((previous) => ({ ...previous, [id]: "clean" })); }}>撤销</button>
                  <button type="button" disabled={(!dirty && !cue.is_source_edited && !cue.is_translation_edited) || state === "saving"} onClick={() => resetCue(cue)}>重置</button>
                  <button type="button" className="editor-history-toggle" onClick={() => setExpanded((previous) => ({ ...previous, [id]: !previous[id] }))}>{expanded[id] ? "收起处理记录" : "查看处理记录"}</button>
                </div>
                {expanded[id] && <dl className="editor-history"><dt>Whisper 原始</dt><dd>{cue.raw_text || "无"}</dd><dt>DeepSeek 校对</dt><dd>{cue.corrected_text || "无"}</dd><dt>DeepSeek 翻译</dt><dd>{cue.translated_text || "无"}</dd><dt>人工修改</dt><dd>{[cue.edited_source_text, cue.edited_translated_text].filter(Boolean).join("\n") || "无"}</dd></dl>}
              </article>
            );
          })}
          {!filtered.length && <p className="editor-empty">没有匹配的字幕。</p>}
        </div>
      )}
    </section>
  );
}
