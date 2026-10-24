// One camera-span contract for shared links and all interactive zoom paths.
// Span is the orthographic view's vertical extent in metres, not zoom level.
export const MIN_VIEW_SPAN = 40;
export const MAX_VIEW_SPAN = 50000;
export function clampViewSpan(value, fallback = 1700) {
  const parsed = Number(value), previous = Number(fallback);
  const span = Number.isFinite(parsed) ? parsed : Number.isFinite(previous) ? previous : 1700;
  return Math.max(MIN_VIEW_SPAN, Math.min(MAX_VIEW_SPAN, span));
}
