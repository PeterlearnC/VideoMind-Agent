import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  CUE_TIME_EPSILON,
  createPlaybackClock,
  findActiveCue,
  findActiveCueId,
} from "../src/subtitleTiming.js";

const cues = [
  { id: 0, start: 0, end: 2.88 },
  { id: 1, start: 2.88, end: 5 },
  { id: 2, start: 6, end: 8 },
];

test("shared cue timing handles zero, exact boundaries, gaps, and final epsilon", () => {
  assert.equal(findActiveCueId(cues, 0), "0");
  assert.equal(findActiveCueId(cues, 2.879), "0");
  assert.equal(findActiveCueId(cues, 2.881), "1");
  assert.equal(findActiveCueId(cues, 5.5), null);
  assert.equal(findActiveCueId(cues, 8 + CUE_TIME_EPSILON / 2), "2");
});

test("seek sync publishes the current media time immediately", () => {
  let mediaTime = 30;
  const published = [];
  const clock = createPlaybackClock({
    readTime: () => mediaTime,
    publishTime: (time) => published.push(time),
    requestFrame: () => 1,
    cancelFrame: () => {},
  });
  clock.sync();
  mediaTime = 60;
  clock.sync();
  assert.deepEqual(published, [30, 60]);
});

test("play creates one RAF loop and pause cancels it", () => {
  const frames = [];
  const cancelled = [];
  const clock = createPlaybackClock({
    readTime: () => 1,
    publishTime: () => {},
    requestFrame: (callback) => { frames.push(callback); return frames.length; },
    cancelFrame: (id) => cancelled.push(id),
  });
  clock.play();
  clock.play();
  assert.equal(frames.length, 1);
  assert.equal(clock.isRunning(), true);
  clock.pause();
  assert.equal(clock.isRunning(), false);
  assert.deepEqual(cancelled, [1]);
});

test("play resumes RAF after pause and dispose cancels on unmount", () => {
  const cancelled = [];
  let nextId = 0;
  const clock = createPlaybackClock({
    readTime: () => 1,
    publishTime: () => {},
    requestFrame: () => { nextId += 1; return nextId; },
    cancelFrame: (id) => cancelled.push(id),
  });
  clock.play();
  clock.pause();
  clock.play();
  assert.equal(clock.isRunning(), true);
  clock.dispose();
  assert.equal(clock.isRunning(), false);
  assert.deepEqual(cancelled, [1, 2]);
});

test("VideoPlayer and SubtitleEditor share the same cue finder", () => {
  const trackPath = fileURLToPath(new URL("../src/components/SubtitleTrack.jsx", import.meta.url));
  const editorPath = fileURLToPath(new URL("../src/components/SubtitleEditor.jsx", import.meta.url));
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const track = readFileSync(trackPath, "utf-8");
  const editor = readFileSync(editorPath, "utf-8");
  const player = readFileSync(playerPath, "utf-8");
  assert.match(track, /activeSubtitle/);
  assert.match(editor, /findActiveCueId\(cues, currentTime\)/);
  assert.match(player, /findActiveCueId\(subtitlesRef\.current, nextTime\)/);
  assert.match(player, /requestAnimationFrame/);
  assert.match(player, /onSeeking=\{handleExplicitTimeChange\}/);
  assert.match(player, /publishPlaybackPosition\(event\.currentTarget\.currentTime, true\)/);
  assert.doesNotMatch(player, /setTimeout\([^)]*,\s*(?:200|500)\)/);
});

test("auto-scroll pause never changes shared active cue calculation", () => {
  assert.equal(findActiveCue(cues, 2.881)?.id, 1);
});
