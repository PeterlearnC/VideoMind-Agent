import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  AUTO_SCROLL_RESUME_DELAY,
  ACTIVE_CUE_ANCHOR_RATIO,
  activeCueId,
  calculateRelativeItemBounds,
  internalScrollTarget,
  shouldAutoScroll,
} from "../src/subtitleAutoScroll.js";

test("active cue remains derived while scrolling is paused", () => {
  const cues = [{ id: 1, start: 0, end: 2 }, { id: 2, start: 2, end: 4 }];
  assert.equal(activeCueId(cues, 2.5), "2");
  assert.equal(shouldAutoScroll({ userScrolling: true, editing: false, query: "" }), false);
});

function elementRect(top, bottom) {
  return { getBoundingClientRect: () => ({ top, bottom, height: bottom - top }) };
}

function scrollContainer({
  top = 800,
  scrollTop = 500,
  clientHeight = 300,
  clientTop = 0,
  scrollHeight = 2000,
} = {}) {
  return {
    scrollTop,
    clientHeight,
    clientTop,
    scrollHeight,
    getBoundingClientRect: () => ({ top }),
  };
}

test("page-level offset is converted into editor-list scroll coordinates", () => {
  const container = scrollContainer();
  assert.deepEqual(
    calculateRelativeItemBounds(container, elementRect(1000, 1070)),
    { top: 700, bottom: 770, height: 70 },
  );
});

test("changing page position does not change the same internal item position", () => {
  const first = calculateRelativeItemBounds(
    scrollContainer({ top: 800 }), elementRect(1000, 1070),
  );
  const second = calculateRelativeItemBounds(
    scrollContainer({ top: 300 }), elementRect(500, 570),
  );
  assert.deepEqual(first, second);
});

test("non-zero scrollTop and container border are included correctly", () => {
  const container = scrollContainer({ top: 800, scrollTop: 500, clientTop: 2 });
  assert.deepEqual(
    calculateRelativeItemBounds(container, elementRect(1002, 1072)),
    { top: 700, bottom: 770, height: 70 },
  );
});

test("middle cue center is anchored at thirty percent of the viewport", () => {
  const container = scrollContainer({
    top: 800, scrollTop: 500, clientHeight: 600, scrollHeight: 3000,
  });
  const item = elementRect(1180, 1260);
  const target = internalScrollTarget(container, item);
  const bounds = calculateRelativeItemBounds(container, item);
  assert.equal(ACTIVE_CUE_ANCHOR_RATIO, 0.30);
  assert.equal(bounds.top + bounds.height / 2 - target, 180);
});

test("active cue is anchored even when it is already visible", () => {
  const container = scrollContainer();
  assert.equal(internalScrollTarget(container, elementRect(900, 970)), 545);
});

test("opening cue target clamps to zero", () => {
  const container = scrollContainer({ top: 800, scrollTop: 0, clientHeight: 600 });
  assert.equal(internalScrollTarget(container, elementRect(810, 890)), 0);
});

test("ending cue target clamps to maxScrollTop", () => {
  const container = scrollContainer({
    top: 800, scrollTop: 1200, clientHeight: 600, scrollHeight: 2000,
  });
  assert.equal(internalScrollTarget(container, elementRect(1450, 1530)), 1400);
});

test("wheel and scroll pause auto follow until the resume delay", () => {
  assert.equal(AUTO_SCROLL_RESUME_DELAY, 2000);
  for (const userScrolling of [true]) {
    assert.equal(shouldAutoScroll({ userScrolling, editing: false, query: "" }), false);
  }
  assert.equal(shouldAutoScroll({ userScrolling: false, editing: false, query: "" }), true);
});

test("textarea focus pauses and blur recovery permits auto follow", () => {
  assert.equal(shouldAutoScroll({ userScrolling: false, editing: true, query: "" }), false);
  assert.equal(shouldAutoScroll({ userScrolling: false, editing: false, query: "" }), true);
});

test("search query pauses auto follow", () => {
  assert.equal(shouldAutoScroll({ userScrolling: false, editing: false, query: "cement" }), false);
});

test("SubtitleEditor never uses page-scrolling APIs", () => {
  const path = fileURLToPath(new URL("../src/components/SubtitleEditor.jsx", import.meta.url));
  const source = readFileSync(path, "utf-8");
  assert.doesNotMatch(source, /scrollIntoView/);
  assert.doesNotMatch(source, /window\.scrollTo|document\.documentElement\.scrollTop|body\.scrollTop/);
  assert.match(source, /listRef\.current/);
  assert.match(source, /window\.addEventListener\("wheel"/);
  assert.match(source, /window\.addEventListener\("scroll"/);
  assert.match(source, /onFocus=\{pauseForEditing\}/);
  assert.match(source, /onBlur=\{resumeAfterEditing\}/);
  assert.match(source, /query,/);
});

test("auto-scroll geometry never depends on offsetTop or offsetHeight", () => {
  const path = fileURLToPath(new URL("../src/subtitleAutoScroll.js", import.meta.url));
  const source = readFileSync(path, "utf-8");
  assert.doesNotMatch(source, /offsetTop|offsetHeight/);
  assert.match(source, /getBoundingClientRect/);
  assert.match(source, /clientTop/);
});

test("SubtitleEditor scroll effect is gated by active cue id changes", () => {
  const path = fileURLToPath(new URL("../src/components/SubtitleEditor.jsx", import.meta.url));
  const source = readFileSync(path, "utf-8");
  assert.match(source, /activeId !== activeIdRef\.current/);
  assert.match(source, /activeIdRef\.current = activeId/);
  assert.equal((source.match(/container\.scrollTo\(/g) || []).length, 1);
});
