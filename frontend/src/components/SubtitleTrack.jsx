export default function SubtitleTrack({
  activeSubtitle = null,
  enabled = true,
  displayMode = "bilingual",
  fontSize = 20,
}) {
  if (!enabled || !activeSubtitle) {
    return null;
  }

  const showSource = displayMode !== "translation";
  const showTranslation = displayMode !== "source";

  return (
    <div
      className="subtitle-track"
      style={{ "--subtitle-font-size": `${fontSize}px` }}
      aria-live="polite"
      aria-atomic="true"
    >
      {showSource && (activeSubtitle.edited_source_text ?? activeSubtitle.corrected_text ?? activeSubtitle.source_text ?? activeSubtitle.source) && (
        <span className="subtitle-source">
          {activeSubtitle.edited_source_text ?? activeSubtitle.corrected_text ?? activeSubtitle.source_text ?? activeSubtitle.source}
        </span>
      )}
      {showTranslation && (activeSubtitle.edited_translated_text ?? activeSubtitle.translated_text ?? activeSubtitle.translation) && (
        <span className="subtitle-translation">
          {activeSubtitle.edited_translated_text ?? activeSubtitle.translated_text ?? activeSubtitle.translation}
        </span>
      )}
    </div>
  );
}
