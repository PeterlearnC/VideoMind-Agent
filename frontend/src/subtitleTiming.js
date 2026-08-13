export const CUE_TIME_EPSILON = 0.02;
export const TIME_SYNC_THRESHOLD = 0.03;

export function findActiveCue(cues, currentTime, epsilon = CUE_TIME_EPSILON) {
  const time = Number(currentTime);
  if (!Number.isFinite(time)) return null;
  return cues.find((cue, index) => {
    const start = Number(cue.start);
    const end = Number(cue.end);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return false;
    const lastCue = index === cues.length - 1;
    const afterStart = time >= start;
    const beforeEnd = lastCue ? time <= end + epsilon : time < end;
    return afterStart && beforeEnd;
  }) || null;
}

export function findActiveCueId(cues, currentTime) {
  const cue = findActiveCue(cues, currentTime);
  return cue ? String(cue.id) : null;
}

export function createPlaybackClock({ readTime, publishTime, requestFrame, cancelFrame }) {
  let frameId = null;
  let playing = false;
  let lastPublished = Number.NaN;

  function sync(force = false) {
    const nextTime = Number(readTime());
    if (!Number.isFinite(nextTime)) return;
    if (force || !Number.isFinite(lastPublished) || Math.abs(nextTime - lastPublished) >= TIME_SYNC_THRESHOLD) {
      lastPublished = nextTime;
      publishTime(nextTime);
    }
  }

  function tick() {
    if (!playing) return;
    sync();
    frameId = requestFrame(tick);
  }

  return {
    play() {
      sync(true);
      if (playing) return;
      playing = true;
      frameId = requestFrame(tick);
    },
    pause() {
      playing = false;
      if (frameId !== null) cancelFrame(frameId);
      frameId = null;
      sync(true);
    },
    sync() {
      sync(true);
    },
    dispose() {
      playing = false;
      if (frameId !== null) cancelFrame(frameId);
      frameId = null;
    },
    isRunning() {
      return playing;
    },
  };
}
