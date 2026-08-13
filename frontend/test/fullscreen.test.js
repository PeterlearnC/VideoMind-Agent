import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  enterElementFullscreen,
  exitDocumentFullscreen,
  isElementFullscreen,
  toggleElementFullscreen,
} from "../src/fullscreen.js";

test("fullscreen is requested on the video stage element", async () => {
  const calls = [];
  const stage = { requestFullscreen() { calls.push("stage"); } };
  const documentRef = { fullscreenElement: null };
  assert.equal(await toggleElementFullscreen(stage, documentRef), true);
  assert.deepEqual(calls, ["stage"]);
});

test("webkit request fallback targets the same stage", async () => {
  let requested = false;
  const stage = { webkitRequestFullscreen() { requested = true; } };
  assert.equal(await enterElementFullscreen(stage), true);
  assert.equal(requested, true);
});

test("active stage fullscreen toggles through document exit", async () => {
  const stage = {};
  let exits = 0;
  const documentRef = {
    fullscreenElement: stage,
    exitFullscreen() { exits += 1; },
  };
  assert.equal(isElementFullscreen(stage, documentRef), true);
  assert.equal(await toggleElementFullscreen(stage, documentRef), true);
  assert.equal(exits, 1);
});

test("webkit document exit fallback is supported", async () => {
  let exits = 0;
  const documentRef = { webkitExitFullscreen() { exits += 1; } };
  assert.equal(await exitDocumentFullscreen(documentRef), true);
  assert.equal(exits, 1);
});

test("video stage subtree contains stable video, subtitle track and controls", () => {
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const player = readFileSync(playerPath, "utf-8");
  const stageStart = player.indexOf('<div ref={videoStageRef} className="video-stage">');
  const stableVideo = player.indexOf("<StableVideoElement", stageStart);
  const subtitleTrack = player.indexOf("<SubtitleTrack", stableVideo);
  const subtitleControl = player.indexOf("<SubtitleControl", subtitleTrack);
  const sectionEnd = player.indexOf('<p className="player-caption">', subtitleControl);
  assert.ok(stageStart >= 0);
  assert.ok(stableVideo > stageStart);
  assert.ok(subtitleTrack > stableVideo);
  assert.ok(subtitleControl > subtitleTrack);
  assert.ok(sectionEnd > subtitleControl);
});

test("fullscreen handler targets videoStageRef and never the video node", () => {
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const player = readFileSync(playerPath, "utf-8");
  assert.match(player, /toggleElementFullscreen\(videoStageRef\.current, document\)/);
  assert.doesNotMatch(player, /toggleElementFullscreen\(videoRef\.current/);
  assert.doesNotMatch(player, /videoRef\.current\.requestFullscreen/);
});

test("fullscreenchange synchronizes state and triggers geometry reclamp", () => {
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const trackPath = fileURLToPath(new URL("../src/components/SubtitleTrack.jsx", import.meta.url));
  const player = readFileSync(playerPath, "utf-8");
  const track = readFileSync(trackPath, "utf-8");
  assert.match(player, /addEventListener\("fullscreenchange", syncFullscreenState\)/);
  assert.match(player, /addEventListener\("webkitfullscreenchange", syncFullscreenState\)/);
  assert.match(player, /setFullscreenLayoutRevision\(\(revision\) => revision \+ 1\)/);
  assert.match(track, /layoutRevision, clampToFrame/);
});

test("fullscreen does not reset subtitle preferences or media state", () => {
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const player = readFileSync(playerPath, "utf-8");
  const handlerStart = player.indexOf("const handleFullscreenToggle");
  const handlerEnd = player.indexOf("const activeSubtitle", handlerStart);
  const handler = player.slice(handlerStart, handlerEnd);
  assert.doesNotMatch(handler, /setSubtitlePreferences|playbackRate|currentTime|seek|clockRef|setActiveCueId/);
  assert.doesNotMatch(handler, /\.play\(|\.pause\(|\.load\(/);
});

test("fullscreen never remounts or keys the stable video element", () => {
  const playerPath = fileURLToPath(new URL("../src/components/VideoPlayer.jsx", import.meta.url));
  const stablePath = fileURLToPath(new URL("../src/components/StableVideoElement.jsx", import.meta.url));
  const player = readFileSync(playerPath, "utf-8");
  const stable = readFileSync(stablePath, "utf-8");
  assert.doesNotMatch(player, /key=\{(?:isFullscreen|fullscreenLayoutRevision)/);
  assert.match(stable, /export default memo\(StableVideoElement\)/);
  assert.doesNotMatch(stable, /fullscreen|activeCue|currentTime/);
});

test("fullscreen CSS promotes the stage and keeps subtitle above video", () => {
  const stylesPath = fileURLToPath(new URL("../src/styles.css", import.meta.url));
  const styles = readFileSync(stylesPath, "utf-8");
  assert.match(styles, /\.video-stage\s*\{[\s\S]*?position:\s*relative;/);
  assert.match(styles, /\.video-stage:fullscreen/);
  assert.match(styles, /\.video-stage:-webkit-full-screen/);
  assert.match(styles, /\.subtitle-track\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?z-index:\s*1;/);
  assert.doesNotMatch(styles, /\.subtitle-track\s*\{[\s\S]*?position:\s*fixed;/);
});

test("custom fullscreen control is present without removing native controls", () => {
  const controlPath = fileURLToPath(new URL("../src/components/SubtitleControl.jsx", import.meta.url));
  const stablePath = fileURLToPath(new URL("../src/components/StableVideoElement.jsx", import.meta.url));
  const control = readFileSync(controlPath, "utf-8");
  const stable = readFileSync(stablePath, "utf-8");
  assert.match(control, /className="player-fullscreen-control"/);
  assert.match(control, /全屏（字幕可见）/);
  assert.match(stable, /\bcontrols\b/);
});
