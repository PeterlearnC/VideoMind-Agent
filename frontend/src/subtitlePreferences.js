export const SUBTITLE_PREFERENCES_KEY = "videomind.subtitlePreferences";
export const DEFAULT_SUBTITLE_POSITION = Object.freeze({
  xPercent: 50,
  yPercent: 80,
});
export const DEFAULT_SUBTITLE_BACKGROUND_OPACITY = 68;
export const DEFAULT_SUBTITLE_FONT_SIZE = 20;

export function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

export function clampSubtitlePosition(position, containerRect, subtitleRect) {
  const width = Number(containerRect?.width) || 0;
  const height = Number(containerRect?.height) || 0;
  if (width <= 0 || height <= 0) return { ...DEFAULT_SUBTITLE_POSITION };

  const halfWidthPercent = Math.min(50, ((Number(subtitleRect?.width) || 0) / 2 / width) * 100);
  const halfHeightPercent = Math.min(50, ((Number(subtitleRect?.height) || 0) / 2 / height) * 100);
  return {
    xPercent: clamp(Number(position.xPercent), halfWidthPercent, 100 - halfWidthPercent),
    yPercent: clamp(Number(position.yPercent), halfHeightPercent, 100 - halfHeightPercent),
  };
}

export function positionFromPointer({
  clientX,
  clientY,
  containerRect,
  subtitleRect,
  grabOffset = { x: 0, y: 0 },
}) {
  const width = Number(containerRect?.width) || 0;
  const height = Number(containerRect?.height) || 0;
  if (width <= 0 || height <= 0) return { ...DEFAULT_SUBTITLE_POSITION };
  const centerX = clientX - containerRect.left - grabOffset.x;
  const centerY = clientY - containerRect.top - grabOffset.y;
  return clampSubtitlePosition(
    {
      xPercent: (centerX / width) * 100,
      yPercent: (centerY / height) * 100,
    },
    containerRect,
    subtitleRect,
  );
}

function validPosition(position) {
  const xPercent = Number(position?.xPercent);
  const yPercent = Number(position?.yPercent);
  if (!Number.isFinite(xPercent) || !Number.isFinite(yPercent)) {
    return { ...DEFAULT_SUBTITLE_POSITION };
  }
  return {
    xPercent: clamp(xPercent, 0, 100),
    yPercent: clamp(yPercent, 0, 100),
  };
}

export function normalizeSubtitlePreferences(value = {}) {
  const backgroundOpacity = Number(value.backgroundOpacity);
  const fontSize = Number(value.fontSize);
  return {
    position: validPosition(value.position),
    backgroundOpacity: Number.isFinite(backgroundOpacity)
      ? clamp(backgroundOpacity, 0, 100)
      : DEFAULT_SUBTITLE_BACKGROUND_OPACITY,
    fontSize: Number.isFinite(fontSize)
      ? clamp(fontSize, 14, 32)
      : DEFAULT_SUBTITLE_FONT_SIZE,
  };
}

export function loadSubtitlePreferences(storage = globalThis.localStorage) {
  try {
    const saved = JSON.parse(storage?.getItem(SUBTITLE_PREFERENCES_KEY) || "null");
    return normalizeSubtitlePreferences(saved || {});
  } catch {
    return normalizeSubtitlePreferences();
  }
}

export function saveSubtitlePreferences(preferences, storage = globalThis.localStorage) {
  try {
    storage?.setItem(
      SUBTITLE_PREFERENCES_KEY,
      JSON.stringify(normalizeSubtitlePreferences(preferences)),
    );
  } catch {
    // UI preferences are best-effort and must never interrupt playback.
  }
}
