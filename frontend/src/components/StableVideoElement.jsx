import { memo } from "react";

function StableVideoElement({
  videoRef,
  src,
  onTimeUpdate,
  onSeeking,
  onSeeked,
  onLoadedMetadata,
  onRateChange,
  onPlay,
  onPause,
  onEnded,
}) {
  return (
    <video
      ref={videoRef}
      className="video-player"
      src={src}
      controls
      playsInline
      preload="metadata"
      onTimeUpdate={onTimeUpdate}
      onSeeking={onSeeking}
      onSeeked={onSeeked}
      onLoadedMetadata={onLoadedMetadata}
      onRateChange={onRateChange}
      onPlay={onPlay}
      onPause={onPause}
      onEnded={onEnded}
    >
      你的浏览器不支持 HTML5 视频播放。
    </video>
  );
}

export default memo(StableVideoElement);
