import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  competitionDemoCloudAiBlocked,
  normalizeCompetitionDemo,
} from "../src/competitionDemo.js";

const demoPayload = {
  enabled: true,
  api_key_configured: false,
  label: "Preloaded Demo / Competition Demo",
  message: "Competition Demo Mode",
  workspace: {
    video_id: "competition-demo",
    video_name: "competition-demo.mp4",
    source_language: "en",
    target_language: "zh",
  },
  summary: { title: "Demo summary" },
  qa_history: [{ id: 1, answer: "Demo answer", references: [{ start: 11 }] }],
};

test("normalizes the preloaded workspace, summary and Q&A", () => {
  const demo = normalizeCompetitionDemo(demoPayload);
  assert.equal(demo.enabled, true);
  assert.equal(demo.workspace.video_id, "competition-demo");
  assert.equal(demo.summary.title, "Demo summary");
  assert.equal(demo.qaHistory.length, 1);
  assert.equal(competitionDemoCloudAiBlocked(demo), true);
});

test("normal mode remains disabled", () => {
  const demo = normalizeCompetitionDemo({ enabled: false });
  assert.equal(demo.enabled, false);
  assert.equal(competitionDemoCloudAiBlocked(demo), false);
});

test("App restores the demo workspace before the normal local workspace", () => {
  const path = fileURLToPath(new URL("../src/App.jsx", import.meta.url));
  const source = readFileSync(path, "utf-8");
  assert.match(source, /fetch\("\/api\/competition-demo\/status"/);
  assert.match(source, /setCompetitionDemo\(detectedDemo\)/);
  assert.match(source, /competition-demo-banner/);
  assert.match(source, /function selectFile\(candidate\) \{[\s\S]*?if \(demoCloudAiBlocked\)/);
  assert.match(source, /function clearFile\(\) \{[\s\S]*?if \(demoCloudAiBlocked\)/);
});

test("preloaded Summary and Q&A remain visible while new cloud requests are disabled", () => {
  const summaryPath = fileURLToPath(new URL("../src/components/SummaryPanel.jsx", import.meta.url));
  const qaPath = fileURLToPath(new URL("../src/components/VideoQAPanel.jsx", import.meta.url));
  const summary = readFileSync(summaryPath, "utf-8");
  const qa = readFileSync(qaPath, "utf-8");
  assert.match(summary, /preloadedSummary/);
  assert.match(summary, /disabled=\{status === "loading" \|\| !cloudAiAvailable\}/);
  assert.match(qa, /preloadedHistory/);
  assert.match(qa, /disabled=\{status === "loading" \|\| !cloudAiAvailable\}/);
});
