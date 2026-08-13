import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_SUBTITLE_BACKGROUND_OPACITY,
  DEFAULT_SUBTITLE_POSITION,
  SUBTITLE_PREFERENCES_KEY,
  clampSubtitlePosition,
  loadSubtitlePreferences,
  normalizeSubtitlePreferences,
  positionFromPointer,
  saveSubtitlePreferences,
} from "../src/subtitlePreferences.js";

const container = { left: 100, top: 200, width: 1000, height: 500 };
const subtitle = { width: 200, height: 60 };

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    value: (key) => values.get(key),
  };
}

test("default subtitle position remains bottom-centered", () => {
  assert.deepEqual(DEFAULT_SUBTITLE_POSITION, { xPercent: 50, yPercent: 80 });
  assert.equal(DEFAULT_SUBTITLE_BACKGROUND_OPACITY, 68);
});

test("pointer coordinates update position as percentages", () => {
  assert.deepEqual(positionFromPointer({
    clientX: 600,
    clientY: 350,
    containerRect: container,
    subtitleRect: subtitle,
  }), { xPercent: 50, yPercent: 30 });
});

test("all four edges clamp the complete subtitle inside the frame", () => {
  assert.deepEqual(clampSubtitlePosition({ xPercent: -5, yPercent: -5 }, container, subtitle), {
    xPercent: 10,
    yPercent: 6,
  });
  assert.deepEqual(clampSubtitlePosition({ xPercent: 105, yPercent: 105 }, container, subtitle), {
    xPercent: 90,
    yPercent: 94,
  });
});

test("background opacity supports transparent and opaque endpoints", () => {
  assert.equal(normalizeSubtitlePreferences({ backgroundOpacity: 0 }).backgroundOpacity, 0);
  assert.equal(normalizeSubtitlePreferences({ backgroundOpacity: 100 }).backgroundOpacity, 100);
});

test("preferences save and restore position opacity and font size", () => {
  const storage = memoryStorage();
  const preferences = {
    position: { xPercent: 25, yPercent: 35 },
    backgroundOpacity: 40,
    fontSize: 28,
  };
  saveSubtitlePreferences(preferences, storage);
  assert.deepEqual(loadSubtitlePreferences(storage), preferences);
  assert.deepEqual(JSON.parse(storage.value(SUBTITLE_PREFERENCES_KEY)), preferences);
});

test("malformed saved preferences safely restore defaults", () => {
  const storage = memoryStorage({ [SUBTITLE_PREFERENCES_KEY]: "not-json" });
  assert.deepEqual(loadSubtitlePreferences(storage).position, DEFAULT_SUBTITLE_POSITION);
});

test("drag implementation uses pointer capture and never invokes media seek", () => {
  const trackPath = fileURLToPath(new URL("../src/components/SubtitleTrack.jsx", import.meta.url));
  const track = readFileSync(trackPath, "utf-8");
  assert.match(track, /onPointerDown=/);
  assert.match(track, /onPointerMove=/);
  assert.match(track, /onPointerUp=/);
  assert.match(track, /setPointerCapture/);
  assert.match(track, /preventDefault\(\)/);
  assert.match(track, /stopPropagation\(\)/);
  assert.doesNotMatch(track, /currentTime|seekRequest|\.play\(|\.pause\(/);
  assert.doesNotMatch(track, /scrollIntoView|window\.scrollTo/);
});

test("cue and language changes do not reset subtitle preferences", () => {
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const player = readFileSync(playerPath, "utf-8");
  assert.match(player, /useState\(\s*loadSubtitlePreferences/);
  assert.doesNotMatch(player, /setSubtitlePreferences[\s\S]{0,150}\[activeCueId/);
  assert.doesNotMatch(player, /setSubtitlePreferences[\s\S]{0,150}\[sourceLanguage, targetLanguage/);
  assert.doesNotMatch(player, /key=\{(?:activeCueId|displayMode|currentTime)\}/);
});

test("reset uses the default percentage position and background uses a CSS variable", () => {
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const stylesPath = fileURLToPath(new URL("../src/styles.css", import.meta.url));
  const player = readFileSync(playerPath, "utf-8");
  const styles = readFileSync(stylesPath, "utf-8");
  assert.match(player, /position: \{ \.\.\.DEFAULT_SUBTITLE_POSITION \}/);
  assert.match(styles, /rgba\(0, 0, 0, var\(--subtitle-bg-opacity, 0\.68\)\)/);
});

test("dragging preferences do not touch playback rate or playback clock", () => {
  const preferencesPath = fileURLToPath(new URL("../src/subtitlePreferences.js", import.meta.url));
  const preferences = readFileSync(preferencesPath, "utf-8");
  assert.doesNotMatch(preferences, /playbackRate|requestAnimationFrame|currentTime/);
});
