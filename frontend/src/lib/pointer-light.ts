/**
 * Moves the "light" of the glass rims a little with the pointer: writes --lx and --ly (0..1 across the window) on
 * <html>. Updates are coalesced into one animation frame and quantised, so a moving mouse restyles rarely, and
 * nothing runs while the pointer is still.
 */
const STEP = 0.04;

export function startPointerLight(): () => void {
  const root = document.documentElement;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return () => undefined;
  let lx = 0.3;
  let ly = 0.2;
  let nextX = lx;
  let nextY = ly;
  let queued = false;

  const flush = () => {
    queued = false;
    const qx = Math.round(nextX / STEP) * STEP;
    const qy = Math.round(nextY / STEP) * STEP;
    if (qx === lx && qy === ly) return;
    lx = qx;
    ly = qy;
    root.style.setProperty("--lx", lx.toFixed(2));
    root.style.setProperty("--ly", ly.toFixed(2));
  };
  const onMove = (event: PointerEvent) => {
    nextX = event.clientX / window.innerWidth;
    nextY = event.clientY / window.innerHeight;
    if (!queued) {
      queued = true;
      requestAnimationFrame(flush);
    }
  };
  window.addEventListener("pointermove", onMove, { passive: true });
  return () => window.removeEventListener("pointermove", onMove);
}
