import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  PLAYBACK_RATE_OPTIONS,
  readMediaPlaybackRate,
  setMediaPlaybackRate,
} from "../src/playbackRate.js";
import { createPlaybackClock, findActiveCueId } from "../src/subtitleTiming.js";

function createVideo({ paused = true } = {}) {
  return {
    currentTime: 1,
    paused,
    playbackRate: 1,
    pauseCalls: 0,
    pause() {
      this.pauseCalls += 1;
      this.paused = true;
    },
  };
}

test("supported playback rates include the complete player menu", () => {
  assert.deepEqual(PLAYBACK_RATE_OPTIONS, [0.5, 0.75, 1, 1.25, 1.5, 2]);
});

test("playback rate changes while paused", () => {
  const video = createVideo();
  assert.equal(setMediaPlaybackRate(video, 1.5), 1.5);
  assert.equal(video.playbackRate, 1.5);
  assert.equal(video.paused, true);
});

test("playback rate changes during playback without pausing", () => {
  const video = createVideo({ paused: false });
  setMediaPlaybackRate(video, 2);
  setMediaPlaybackRate(video, 0.75);
  assert.equal(video.playbackRate, 0.75);
  assert.equal(video.paused, false);
  assert.equal(video.pauseCalls, 0);
});

test("native rate values can synchronize React state", () => {
  const video = createVideo();
  video.playbackRate = 1.25;
  assert.equal(readMediaPlaybackRate(video), 1.25);
});

test("rate changes do not alter media time or active cue", () => {
  const video = createVideo({ paused: false });
  video.currentTime = 3;
  const cues = [{ id: 0, start: 0, end: 2 }, { id: 1, start: 2, end: 4 }];
  const before = findActiveCueId(cues, video.currentTime);
  setMediaPlaybackRate(video, 2);
  assert.equal(video.currentTime, 3);
  assert.equal(findActiveCueId(cues, video.currentTime), before);
});

test("rate changes do not create a second RAF loop", () => {
  const video = createVideo({ paused: false });
  const frames = [];
  const clock = createPlaybackClock({
    readTime: () => video.currentTime,
    publishTime: () => {},
    requestFrame: (callback) => { frames.push(callback); return frames.length; },
    cancelFrame: () => {},
  });
  clock.play();
  setMediaPlaybackRate(video, 1.5);
  setMediaPlaybackRate(video, 2);
  assert.equal(frames.length, 1);
  assert.equal(clock.isRunning(), true);
});

test("player exposes an enabled rate control and native ratechange synchronization", () => {
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const controlsPath = fileURLToPath(new URL("../src/components/SubtitleControl.jsx", import.meta.url));
  const player = readFileSync(playerPath, "utf-8");
  const controls = readFileSync(controlsPath, "utf-8");
  assert.match(controls, /aria-label="播放倍速"/);
  assert.match(controls, /PLAYBACK_RATE_OPTIONS\.map/);
  assert.match(player, /onPlaybackRateChange=\{handlePlaybackRateChange\}/);
  assert.match(player, /onRateChange=\{handleNativeRateChange\}/);
  assert.doesNotMatch(controls, /<select[\s\S]{0,200}disabled=/);
  assert.doesNotMatch(controls, /key=\{(?:currentTime|activeCueId)\}/);
  assert.doesNotMatch(player, /handlePlaybackRateChange[\s\S]{0,300}\.pause\(/);
});

test("rate control remains pointer-enabled above overlays", () => {
  const stylesPath = fileURLToPath(new URL("../src/styles.css", import.meta.url));
  const styles = readFileSync(stylesPath, "utf-8");
  assert.match(styles, /\.playback-rate-control\s*\{[\s\S]*?pointer-events:\s*auto;/);
});

test("stable video element is isolated from playback clock and active cue renders", () => {
  const stablePath = fileURLToPath(new URL("../src/components/StableVideoElement.jsx", import.meta.url));
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const stable = readFileSync(stablePath, "utf-8");
  const player = readFileSync(playerPath, "utf-8");
  assert.match(stable, /export default memo\(StableVideoElement\)/);
  assert.doesNotMatch(stable, /currentTime|activeCue|subtitles/);
  assert.doesNotMatch(stable, /key=/);
  assert.doesNotMatch(player, /<video\b/);
  assert.doesNotMatch(player, /key=\{(?:currentTime|activeCueId|src)\}/);
});

test("RAF publishes to App only when the active cue changes", () => {
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const appPath = fileURLToPath(new URL("../src/App.jsx", import.meta.url));
  const player = readFileSync(playerPath, "utf-8");
  const app = readFileSync(appPath, "utf-8");
  assert.match(player, /nextActiveCueId !== publishedActiveCueIdRef\.current/);
  assert.match(player, /onActiveCueChangeRef\.current\?\.\(nextActiveCueId, nextTime\)/);
  assert.doesNotMatch(player, /setCurrentTime\(/);
  assert.match(app, /onActiveCueChange=\{handleActiveCueChange\}/);
  assert.doesNotMatch(app, /onTimeChange=\{setPlayerCurrentTime\}/);
});

test("cue and seek updates preserve the media node and playback rate", () => {
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const player = readFileSync(playerPath, "utf-8");
  assert.match(player, /playbackRateRef\.current/);
  assert.match(player, /setMediaPlaybackRate\(event\.currentTarget, playbackRateRef\.current\)/);
  assert.doesNotMatch(player, /videoRef\.current\s*=/);
  assert.doesNotMatch(player, /\.load\(\)/);
});

test("five consecutive cue changes leave the selected playback rate untouched", () => {
  const video = createVideo({ paused: false });
  setMediaPlaybackRate(video, 1.5);
  const cues = Array.from({ length: 5 }, (_, id) => ({ id, start: id, end: id + 1 }));
  for (let id = 0; id < cues.length; id += 1) {
    video.currentTime = id + 0.5;
    assert.equal(findActiveCueId(cues, video.currentTime), String(id));
    assert.equal(video.playbackRate, 1.5);
    assert.equal(video.paused, false);
  }
});

test("custom rate select lives in the shared subtitle control bar", () => {
  const controlsPath = fileURLToPath(new URL("../src/components/SubtitleControl.jsx", import.meta.url));
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const controls = readFileSync(controlsPath, "utf-8");
  const player = readFileSync(playerPath, "utf-8");
  assert.match(controls, /className="playback-rate-control"/);
  assert.equal((controls.match(/aria-label="播放倍速"/g) || []).length, 1);
  assert.doesNotMatch(player, /aria-label="播放倍速"/);
});
