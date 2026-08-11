import { useEffect, useState } from "react";

import SubtitleControl from "./SubtitleControl";
import SubtitleTrack from "./SubtitleTrack";

export default function VideoPlayer({ src, subtitles = [], title = "视频预览" }) {
  const [currentTime, setCurrentTime] = useState(0);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(true);
  const [displayMode, setDisplayMode] = useState("bilingual");
  const [subtitleFontSize, setSubtitleFontSize] = useState(20);

  useEffect(() => {
    setCurrentTime(0);
  }, [src]);

  if (!src) {
    return null;
  }

  return (
    <section className="player-section" aria-label="视频播放区域">
      <div className="player-heading">
        <div>
          <span className="section-number">03</span>
          <h2>{title}</h2>
        </div>
        <span className="player-time">{currentTime.toFixed(1)}s</span>
      </div>
      <div className="video-frame">
        <video
          key={src}
          className="video-player"
          src={src}
          controls
          playsInline
          preload="metadata"
          onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
          onSeeked={(event) => setCurrentTime(event.currentTarget.currentTime)}
        >
          你的浏览器不支持 HTML5 视频播放。
        </video>
        <SubtitleTrack
          subtitles={subtitles}
          currentTime={currentTime}
          enabled={subtitlesEnabled}
          displayMode={displayMode}
          fontSize={subtitleFontSize}
        />
      </div>
      <SubtitleControl
        enabled={subtitlesEnabled}
        displayMode={displayMode}
        fontSize={subtitleFontSize}
        disabled={subtitles.length === 0}
        onEnabledChange={setSubtitlesEnabled}
        onDisplayModeChange={setDisplayMode}
        onFontSizeChange={setSubtitleFontSize}
      />
      <p className="player-caption">
        {subtitles.length > 0
          ? `已加载 ${subtitles.length} 条双语字幕，字幕会随播放进度实时切换。`
          : "视频已就绪。生成双语字幕后会在画面中实时显示。"}
      </p>
    </section>
  );
}
