import { findActiveCueId } from "./subtitleTiming.js";

export const AUTO_SCROLL_RESUME_DELAY = 2000;
export const AUTO_SCROLL_PADDING = 16;
export const ACTIVE_CUE_ANCHOR_RATIO = 0.30;

export function activeCueId(cues, currentTime) {
  return findActiveCueId(cues, currentTime);
}

export function calculateRelativeItemBounds(container, item) {
  if (!container || !item) return null;
  const containerRect = container.getBoundingClientRect();
  const itemRect = item.getBoundingClientRect();
  const contentTop = containerRect.top + (container.clientTop || 0);
  const top = container.scrollTop + itemRect.top - contentTop;
  const bottom = container.scrollTop + itemRect.bottom - contentTop;
  return { top, bottom, height: itemRect.height ?? itemRect.bottom - itemRect.top };
}

export function internalScrollTarget(
  container,
  item,
  anchorRatio = ACTIVE_CUE_ANCHOR_RATIO,
) {
  const bounds = calculateRelativeItemBounds(container, item);
  if (!bounds) return null;
  const unclampedTarget =
    bounds.top + bounds.height * 0.5 - container.clientHeight * anchorRatio;
  const maxScrollTop = Math.max(0, container.scrollHeight - container.clientHeight);
  return Math.min(maxScrollTop, Math.max(0, unclampedTarget));
}

export function shouldAutoScroll({ userScrolling, editing, query }) {
  return !userScrolling && !editing && !query.trim();
}
