export default function SubtitleTrack({
  subtitles = [],
  currentTime = 0,
  enabled = true,
  displayMode = "bilingual",
  fontSize = 20,
}) {
  const activeSubtitle = subtitles.find(
    (subtitle) =>
      currentTime >= Number(subtitle.start) && currentTime < Number(subtitle.end),
  );

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
      {showSource && activeSubtitle.source && (
        <span className="subtitle-source">{activeSubtitle.source}</span>
      )}
      {showTranslation && activeSubtitle.translation && (
        <span className="subtitle-translation">
          {activeSubtitle.translation}
        </span>
      )}
    </div>
  );
}
