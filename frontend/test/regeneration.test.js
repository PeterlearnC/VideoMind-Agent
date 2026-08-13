import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  confirmRegeneration,
  createRequestGate,
  generationButtonLabel,
  regenerationFailed,
  regenerationSucceeded,
  regenerationWarning,
} from "../src/regeneration.js";

test("generated workspace uses the regenerate label", () => {
  assert.equal(generationButtonLabel(false), "开始生成字幕");
  assert.equal(generationButtonLabel(true), "重新生成字幕");
});

test("clean workspace regenerates without confirmation", () => {
  let confirmations = 0;
  assert.equal(confirmRegeneration(0, () => { confirmations += 1; return false; }), true);
  assert.equal(confirmations, 0);
});

test("dirty workspace shows its count and cancellation prevents regeneration", () => {
  let prompt = "";
  const proceed = confirmRegeneration(3, (message) => { prompt = message; return false; });
  assert.equal(proceed, false);
  assert.equal(prompt, regenerationWarning(3));
  assert.match(prompt, /3 条未保存/);
});

test("confirmation allows one request while the request is running", () => {
  const gate = createRequestGate();
  assert.equal(confirmRegeneration(2, () => true), true);
  assert.equal(gate.enter(), true);
  assert.equal(gate.enter(), false);
  gate.leave();
  assert.equal(gate.enter(), true);
});

test("request gate is released after failure", () => {
  const gate = createRequestGate();
  assert.equal(gate.enter(), true);
  gate.leave();
  assert.equal(gate.enter(), true);
});

test("successful regeneration clears dirty state and discards old drafts", () => {
  const nextCues = [{ id: 1, effective_source_text: "new AI baseline" }];
  assert.deepEqual(regenerationSucceeded(nextCues), {
    subtitles: nextCues,
    dirtyCount: 0,
    discardDrafts: true,
    status: "success",
  });
});

test("failed regeneration preserves the previous workspace and exposes an error", () => {
  const previousCues = [{ id: 1, effective_source_text: "existing subtitle" }];
  const result = regenerationFailed(previousCues, "network unavailable");
  assert.equal(result.subtitles, previousCues);
  assert.equal(result.status, "error");
  assert.match(result.errorMessage, /network unavailable/);
});

test("restored clean workspace reads the active video id before assigning the generated id", () => {
  const appPath = fileURLToPath(new URL("../src/App.jsx", import.meta.url));
  const source = readFileSync(appPath, "utf-8");
  const handler = source.slice(
    source.indexOf("async function handleSubmit"),
    source.indexOf("\n  return (", source.indexOf("async function handleSubmit")),
  );

  assert.match(handler, /encodeURIComponent\(videoId\)/);
  assert.match(handler, /const generatedVideoId = response\.subtitle_file/);
  assert.doesNotMatch(handler, /\b(?:const|let) videoId\b/);
  assert.match(handler, /videoId: generatedVideoId/);
});
