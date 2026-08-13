import { languageLabel } from "../languages";
import { PLAYBACK_RATE_OPTIONS } from "../playbackRate.js";

export default function SubtitleControl({
  enabled,
  displayMode,
  fontSize,
  playbackRate,
  backgroundOpacity,
  disabled = false,
  onEnabledChange,
  onDisplayModeChange,
  onFontSizeChange,
  onPlaybackRateChange,
  onBackgroundOpacityChange,
  onResetPosition,
  sourceLanguage,
  targetLanguage,
}) {
  const monolingual = sourceLanguage === targetLanguage;
  const displayModes = monolingual
    ? [{ value: "source", label: languageLabel(sourceLanguage) }]
    : [
        { value: "bilingual", label: "双语" },
        { value: "source", label: languageLabel(sourceLanguage) },
        { value: "translation", label: languageLabel(targetLanguage) },
      ];
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
          {displayModes.map((mode) => (
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

      <label className="playback-rate-control">
        <span>倍速</span>
        <select
          aria-label="播放倍速"
          value={playbackRate}
          onChange={(event) => onPlaybackRateChange(Number(event.target.value))}
        >
          {PLAYBACK_RATE_OPTIONS.map((rate) => (
            <option key={rate} value={rate}>{rate}x</option>
          ))}
        </select>
      </label>

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

      <label className="subtitle-background">
        <span>背景</span>
        <input
          type="range"
          min="0"
          max="100"
          step="5"
          value={backgroundOpacity}
          disabled={disabled || !enabled}
          aria-label="字幕背景透明度"
          aria-valuetext={`${backgroundOpacity}%`}
          onChange={(event) => onBackgroundOpacityChange(Number(event.target.value))}
        />
        <output>{backgroundOpacity}%</output>
      </label>

      <div className="subtitle-position-control">
        <span>位置</span>
        <button
          type="button"
          disabled={disabled || !enabled}
          onClick={onResetPosition}
        >
          恢复默认
        </button>
      </div>
    </div>
  );
}
