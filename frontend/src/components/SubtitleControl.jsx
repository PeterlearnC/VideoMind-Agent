const DISPLAY_MODES = [
  { value: "bilingual", label: "双语" },
  { value: "source", label: "English" },
  { value: "translation", label: "中文" },
];

export default function SubtitleControl({
  enabled,
  displayMode,
  fontSize,
  disabled = false,
  onEnabledChange,
  onDisplayModeChange,
  onFontSizeChange,
}) {
  return (
    <div className="subtitle-control" aria-label="字幕控制面板">
      <label className="subtitle-switch">
        <input
          type="checkbox"
          checked={enabled}
          disabled={disabled}
          onChange={(event) => onEnabledChange(event.target.checked)}
        />
        <span className="switch-track" aria-hidden="true">
          <span />
        </span>
        <span>字幕</span>
        <strong>{enabled ? "开启" : "关闭"}</strong>
      </label>

      <fieldset className="subtitle-mode" disabled={disabled || !enabled}>
        <legend>显示语言</legend>
        <div>
          {DISPLAY_MODES.map((mode) => (
            <button
              key={mode.value}
              type="button"
              className={displayMode === mode.value ? "is-active" : ""}
              aria-pressed={displayMode === mode.value}
              onClick={() => onDisplayModeChange(mode.value)}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </fieldset>

      <label className="subtitle-size">
        <span>字号</span>
        <input
          type="range"
          min="14"
          max="32"
          step="2"
          value={fontSize}
          disabled={disabled || !enabled}
          aria-valuetext={`${fontSize} 像素`}
          onChange={(event) => onFontSizeChange(Number(event.target.value))}
        />
        <output>{fontSize}px</output>
      </label>
    </div>
  );
}
