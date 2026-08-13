import { useCallback, useEffect, useRef, useState } from "react";

import { clampSubtitlePosition, positionFromPointer } from "../subtitlePreferences.js";

export default function SubtitleTrack({
  activeSubtitle = null,
  enabled = true,
  displayMode = "bilingual",
  fontSize = 20,
  position,
  backgroundOpacity,
  layoutRevision = 0,
  onPositionChange,
}) {
  const trackRef = useRef(null);
  const dragRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const clampToFrame = useCallback(() => {
    const track = trackRef.current;
    const frame = track?.parentElement;
    if (!track || !frame) return;
    const clamped = clampSubtitlePosition(
      position,
      frame.getBoundingClientRect(),
      track.getBoundingClientRect(),
    );
    if (
      clamped.xPercent !== position.xPercent
      || clamped.yPercent !== position.yPercent
    ) {
      onPositionChange(clamped);
    }
  }, [onPositionChange, position]);

  useEffect(() => {
    window.addEventListener("resize", clampToFrame);
    return () => window.removeEventListener("resize", clampToFrame);
  }, [clampToFrame]);

  useEffect(() => {
    clampToFrame();
  }, [activeSubtitle, displayMode, fontSize, layoutRevision, clampToFrame]);

  if (!enabled || !activeSubtitle) {
    return null;
  }

  const showSource = displayMode !== "translation";
  const showTranslation = displayMode !== "source";

  return (
    <div
      ref={trackRef}
      className={`subtitle-track${dragging ? " is-dragging" : ""}`}
      style={{
        "--subtitle-font-size": `${fontSize}px`,
        "--subtitle-bg-opacity": backgroundOpacity / 100,
        left: `${position.xPercent}%`,
        top: `${position.yPercent}%`,
      }}
      aria-live="polite"
      aria-atomic="true"
      onPointerDown={(event) => {
        if (event.button !== undefined && event.button !== 0) return;
        event.preventDefault();
        event.stopPropagation();
        const rect = event.currentTarget.getBoundingClientRect();
        dragRef.current = {
          pointerId: event.pointerId,
          grabOffset: {
            x: event.clientX - (rect.left + rect.width / 2),
            y: event.clientY - (rect.top + rect.height / 2),
          },
        };
        event.currentTarget.setPointerCapture?.(event.pointerId);
        setDragging(true);
      }}
      onPointerMove={(event) => {
        const drag = dragRef.current;
        const frame = event.currentTarget.parentElement;
        if (!drag || drag.pointerId !== event.pointerId || !frame) return;
        event.preventDefault();
        event.stopPropagation();
        onPositionChange(positionFromPointer({
          clientX: event.clientX,
          clientY: event.clientY,
          containerRect: frame.getBoundingClientRect(),
          subtitleRect: event.currentTarget.getBoundingClientRect(),
          grabOffset: drag.grabOffset,
        }));
      }}
      onPointerUp={(event) => {
        if (dragRef.current?.pointerId !== event.pointerId) return;
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.releasePointerCapture?.(event.pointerId);
        dragRef.current = null;
        setDragging(false);
      }}
      onPointerCancel={() => {
        dragRef.current = null;
        setDragging(false);
      }}
    >
      {showSource && (activeSubtitle.edited_source_text ?? activeSubtitle.corrected_text ?? activeSubtitle.source_text ?? activeSubtitle.source) && (
        <span className="subtitle-source">
          {activeSubtitle.edited_source_text ?? activeSubtitle.corrected_text ?? activeSubtitle.source_text ?? activeSubtitle.source}
        </span>
      )}
      {showTranslation && (activeSubtitle.edited_translated_text ?? activeSubtitle.translated_text ?? activeSubtitle.translation) && (
        <span className="subtitle-translation">
          {activeSubtitle.edited_translated_text ?? activeSubtitle.translated_text ?? activeSubtitle.translation}
        </span>
      )}
    </div>
  );
}
