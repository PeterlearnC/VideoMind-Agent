import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import StableVideoElement from "./StableVideoElement";
import SubtitleControl from "./SubtitleControl";
import SubtitleTrack from "./SubtitleTrack";
import {
  readMediaPlaybackRate,
  setMediaPlaybackRate,
} from "../playbackRate.js";
import { createPlaybackClock, findActiveCueId } from "../subtitleTiming.js";
import {
  DEFAULT_SUBTITLE_POSITION,
  loadSubtitlePreferences,
  saveSubtitlePreferences,
} from "../subtitlePreferences.js";

export default function VideoPlayer({
  src,
  subtitles = [],
  title = "视频预览",
  seekRequest = null,
  onActiveCueChange,
  sourceLanguage,
  targetLanguage,
}) {
  const videoRef = useRef(null);
  const clockRef = useRef(null);
  const playerTimeRef = useRef(null);
  const subtitlesRef = useRef(subtitles);
  const onActiveCueChangeRef = useRef(onActiveCueChange);
  const publishedActiveCueIdRef = useRef(undefined);
  const playbackRateRef = useRef(1);
  const [activeCueId, setActiveCueId] = useState(null);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(true);
  const [displayMode, setDisplayMode] = useState("bilingual");
  const [subtitlePreferences, setSubtitlePreferences] = useState(
    loadSubtitlePreferences,
  );
  const { position: subtitlePosition, backgroundOpacity, fontSize: subtitleFontSize } = subtitlePreferences;

  useEffect(() => {
    saveSubtitlePreferences(subtitlePreferences);
  }, [subtitlePreferences]);

  useEffect(() => {
    publishedActiveCueIdRef.current = undefined;
    setActiveCueId(null);
    if (playerTimeRef.current) playerTimeRef.current.textContent = "0.0s";
  }, [src]);

  useEffect(() => {
    subtitlesRef.current = subtitles;
    clockRef.current?.sync();
  }, [subtitles]);

  useEffect(() => {
    onActiveCueChangeRef.current = onActiveCueChange;
  }, [onActiveCueChange]);

  const publishPlaybackPosition = useCallback((nextTime, force = false) => {
    if (playerTimeRef.current) {
      playerTimeRef.current.textContent = `${nextTime.toFixed(1)}s`;
    }
    const nextActiveCueId = findActiveCueId(subtitlesRef.current, nextTime);
    if (nextActiveCueId !== publishedActiveCueIdRef.current) {
      publishedActiveCueIdRef.current = nextActiveCueId;
      setActiveCueId(nextActiveCueId);
      onActiveCueChangeRef.current?.(nextActiveCueId, nextTime);
    } else if (force) {
      onActiveCueChangeRef.current?.(nextActiveCueId, nextTime);
    }
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return undefined;
    const clock = createPlaybackClock({
      readTime: () => video.currentTime,
      publishTime: publishPlaybackPosition,
      requestFrame: window.requestAnimationFrame.bind(window),
      cancelFrame: window.cancelAnimationFrame.bind(window),
    });
    clockRef.current = clock;
    clock.sync();
    return () => {
      clock.dispose();
      if (clockRef.current === clock) clockRef.current = null;
    };
  }, [src, publishPlaybackPosition]);

  useEffect(() => {
    setDisplayMode(
      sourceLanguage && sourceLanguage === targetLanguage
        ? "source"
        : "bilingual",
    );
  }, [sourceLanguage, targetLanguage]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !seekRequest) return;

    video.currentTime = seekRequest.targetTime;
    clockRef.current?.sync();
    publishPlaybackPosition(video.currentTime, true);
    const playPromise = video.play();
    playPromise?.catch(() => {
      // Browsers may still block scripted playback; the seek itself remains valid.
    });
  }, [seekRequest, publishPlaybackPosition]);

  const handleTimeChange = useCallback(() => {
    clockRef.current?.sync();
  }, []);

  const handleExplicitTimeChange = useCallback((event) => {
    clockRef.current?.sync();
    publishPlaybackPosition(event.currentTarget.currentTime, true);
  }, [publishPlaybackPosition]);

  const handlePlaybackRateChange = useCallback((nextRate) => {
    const appliedRate = setMediaPlaybackRate(videoRef.current, nextRate);
    if (appliedRate !== null) {
      playbackRateRef.current = appliedRate;
      setPlaybackRate(appliedRate);
    }
  }, []);

  const handleNativeRateChange = useCallback((event) => {
    const nextRate = readMediaPlaybackRate(event.currentTarget);
    playbackRateRef.current = nextRate;
    setPlaybackRate(nextRate);
  }, []);

  const handleLoadedMetadata = useCallback((event) => {
    setMediaPlaybackRate(event.currentTarget, playbackRateRef.current);
    clockRef.current?.sync();
    publishPlaybackPosition(event.currentTarget.currentTime, true);
  }, [publishPlaybackPosition]);

  const handlePlay = useCallback(() => clockRef.current?.play(), []);
  const handlePause = useCallback(() => clockRef.current?.pause(), []);

  const activeSubtitle = useMemo(
    () => subtitles.find((cue) => String(cue.id) === activeCueId) || null,
    [activeCueId, subtitles],
  );

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
        <span ref={playerTimeRef} className="player-time">0.0s</span>
      </div>
      <div className="video-frame">
        <StableVideoElement
          videoRef={videoRef}
          src={src}
          onTimeUpdate={handleTimeChange}
          onSeeking={handleExplicitTimeChange}
          onSeeked={handleExplicitTimeChange}
          onLoadedMetadata={handleLoadedMetadata}
          onRateChange={handleNativeRateChange}
          onPlay={handlePlay}
          onPause={handlePause}
          onEnded={handlePause}
        />
        <SubtitleTrack
          activeSubtitle={activeSubtitle}
          enabled={subtitlesEnabled}
          displayMode={displayMode}
          fontSize={subtitleFontSize}
          position={subtitlePosition}
          backgroundOpacity={backgroundOpacity}
          onPositionChange={(position) => setSubtitlePreferences((current) => ({
            ...current,
            position,
          }))}
        />
      </div>
      <SubtitleControl
        enabled={subtitlesEnabled}
        displayMode={displayMode}
        fontSize={subtitleFontSize}
        playbackRate={playbackRate}
        disabled={subtitles.length === 0}
        onEnabledChange={setSubtitlesEnabled}
        onDisplayModeChange={setDisplayMode}
        backgroundOpacity={backgroundOpacity}
        onBackgroundOpacityChange={(backgroundOpacity) => setSubtitlePreferences((current) => ({
          ...current,
          backgroundOpacity,
        }))}
        onResetPosition={() => setSubtitlePreferences((current) => ({
          ...current,
          position: { ...DEFAULT_SUBTITLE_POSITION },
        }))}
        onFontSizeChange={(fontSize) => setSubtitlePreferences((current) => ({
          ...current,
          fontSize,
        }))}
        onPlaybackRateChange={handlePlaybackRateChange}
        sourceLanguage={sourceLanguage}
        targetLanguage={targetLanguage}
      />
      <p className="player-caption">
        {subtitles.length > 0
          ? `已加载 ${subtitles.length} 条${sourceLanguage === targetLanguage ? "单语" : "双语"}字幕，字幕会随播放进度实时切换。`
          : "视频已就绪。生成字幕后会在画面中实时显示。"}
      </p>
    </section>
  );
}
