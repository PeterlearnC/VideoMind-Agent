export function fullscreenElement(documentRef = globalThis.document) {
  return documentRef?.fullscreenElement ?? documentRef?.webkitFullscreenElement ?? null;
}

export function isElementFullscreen(element, documentRef = globalThis.document) {
  return Boolean(element && fullscreenElement(documentRef) === element);
}

export async function enterElementFullscreen(element) {
  if (!element) return false;
  const request = element.requestFullscreen ?? element.webkitRequestFullscreen;
  if (typeof request !== "function") return false;
  await request.call(element);
  return true;
}

export async function exitDocumentFullscreen(documentRef = globalThis.document) {
  const exit = documentRef?.exitFullscreen ?? documentRef?.webkitExitFullscreen;
  if (typeof exit !== "function") return false;
  await exit.call(documentRef);
  return true;
}

export async function toggleElementFullscreen(element, documentRef = globalThis.document) {
  if (isElementFullscreen(element, documentRef)) {
    return exitDocumentFullscreen(documentRef);
  }
  return enterElementFullscreen(element);
}
