export const PLAYBACK_RATE_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2];

export function setMediaPlaybackRate(video, nextRate) {
  const rate = Number(nextRate);
  if (!video || !Number.isFinite(rate) || rate <= 0) return null;

  video.playbackRate = rate;
  return video.playbackRate;
}

export function readMediaPlaybackRate(video, fallback = 1) {
  const rate = Number(video?.playbackRate);
  return Number.isFinite(rate) && rate > 0 ? rate : fallback;
}
