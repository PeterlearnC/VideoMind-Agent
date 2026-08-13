export function generationButtonLabel(hasWorkspace) {
  return hasWorkspace ? "重新生成字幕" : "开始生成字幕";
}

export function regenerationWarning(dirtyCount) {
  return `当前还有 ${dirtyCount} 条未保存的字幕修改。\n重新生成字幕将丢失这些未保存内容，是否继续？`;
}

export function confirmRegeneration(dirtyCount, confirmAction) {
  return dirtyCount === 0 || confirmAction(regenerationWarning(dirtyCount));
}

export function createRequestGate() {
  let running = false;
  return {
    enter() {
      if (running) return false;
      running = true;
      return true;
    },
    leave() {
      running = false;
    },
  };
}

export function regenerationSucceeded(nextSubtitles) {
  return {
    subtitles: nextSubtitles,
    dirtyCount: 0,
    discardDrafts: true,
    status: "success",
  };
}

export function regenerationFailed(previousSubtitles, message) {
  return {
    subtitles: previousSubtitles,
    status: "error",
    errorMessage: `重新生成字幕失败：${message || "请稍后重试。"}`,
  };
}
