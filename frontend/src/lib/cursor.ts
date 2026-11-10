/**
 * The custom cursor: a small dot that tracks the mouse exactly and a ring that follows with a short spring, drawn
 * by one fixed element (#cursor, mix-blend-mode: difference, so it inverts over the liquid). Fine pointers only;
 * touch devices and forced-colors keep the system cursor, and with reduced motion only the dot remains.
 *
 * States (data-state): default; hover (ring grows and softly snaps toward the element); text (a thin vertical
 * bar over text fields); press (ring shrinks); grab (dashed ring while files are dragged over the window). It
 * fades out when the pointer leaves the window. The animation loop runs only while something is still moving.
 */
type State = "default" | "hover" | "text" | "press" | "grab";

const HOVER = "a[href],button,[role=button],[role=tab],[role=menuitem],[role=option],summary,select,label[for],[data-cursor=hover]";
const TEXT =
  "textarea,[contenteditable=''],[contenteditable='true'],input:not([type=checkbox],[type=radio],[type=button],[type=submit],[type=reset],[type=range],[type=file],[type=color])";
const STIFFNESS = 320;
const DAMPING = 26;

export function startCursor(): (() => void) | null {
  if (typeof window === "undefined") return null;
  if (!window.matchMedia("(pointer: fine) and (hover: hover)").matches) return null;
  if (window.matchMedia("(forced-colors: active)").matches) return null;

  const root = document.documentElement;
  const el = document.createElement("div");
  el.id = "cursor";
  el.setAttribute("aria-hidden", "true");
  el.dataset.state = "default";
  el.innerHTML = '<i class="c-ring"></i><i class="c-bar"></i><i class="c-dot"></i>';
  document.body.append(el);
  const ring = el.querySelector<HTMLElement>(".c-ring")!;
  const bar = el.querySelector<HTMLElement>(".c-bar")!;
  const dot = el.querySelector<HTMLElement>(".c-dot")!;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

  let mx = -100;
  let my = -100;
  let rx = mx;
  let ry = my;
  let vx = 0;
  let vy = 0;
  let scale = 1;
  let vs = 0;
  let state: State = "default";
  let target: Element | null = null;
  let pressed = false;
  let dragging = false;
  let raf = 0;
  let last = 0;
  let shown = false;

  function kick() {
    if (!raf) raf = requestAnimationFrame(frame);
  }

  function setState(next: State) {
    if (next === state) return;
    state = next;
    el.dataset.state = next;
    kick();
  }

  function resolve() {
    if (dragging) return setState("grab");
    if (pressed) return setState("press");
    if (target?.closest(TEXT)) return setState("text");
    if (target?.closest(HOVER)) return setState("hover");
    setState("default");
  }

  function frame(now: number) {
    const dt = Math.min(0.032, (now - (last || now)) / 1000);
    last = now;

    // Where the ring wants to be and how big.
    let tx = mx;
    let ty = my;
    let ts = 1;
    if (state === "hover") {
      const rect = target?.closest(HOVER)?.getBoundingClientRect();
      if (rect && rect.width < 260 && rect.height < 120) {
        tx = mx + (rect.left + rect.width / 2 - mx) * 0.4;
        ty = my + (rect.top + rect.height / 2 - my) * 0.4;
        ts = 1.9;
      } else ts = 1.6;
    } else if (state === "press") ts = 0.78;
    else if (state === "grab") ts = 1.7;

    // Spring toward the target (semi-implicit Euler, two substeps for stability).
    const steps = 2;
    const h = dt / steps;
    for (let i = 0; i < steps; i++) {
      vx += (STIFFNESS * (tx - rx) - DAMPING * vx) * h;
      vy += (STIFFNESS * (ty - ry) - DAMPING * vy) * h;
      vs += (STIFFNESS * (ts - scale) - DAMPING * vs) * h;
      rx += vx * h;
      ry += vy * h;
      scale += vs * h;
    }

    ring.style.transform = `translate3d(${rx}px,${ry}px,0) scale(${scale.toFixed(3)})`;

    const moving =
      Math.abs(tx - rx) > 0.15 || Math.abs(ty - ry) > 0.15 || Math.abs(ts - scale) > 0.003 || Math.abs(vx) + Math.abs(vy) > 1;
    raf = moving && !reduced.matches ? requestAnimationFrame(frame) : 0;
    if (!raf) last = 0;
  }

  function place() {
    // The dot and the bar track the mouse exactly: written on every pointer event, outside the spring loop.
    dot.style.transform = `translate3d(${mx}px,${my}px,0)`;
    bar.style.transform = `translate3d(${mx}px,${my}px,0)`;
    if (reduced.matches) ring.style.transform = `translate3d(${mx}px,${my}px,0)`;
    else kick();
  }

  function show() {
    if (shown) return;
    shown = true;
    el.dataset.visible = "true";
    root.classList.add("has-cursor");
  }

  const onMove = (event: PointerEvent) => {
    if (event.pointerType !== "mouse") return;
    mx = event.clientX;
    my = event.clientY;
    if (!shown) {
      rx = mx;
      ry = my;
      show();
    }
    place();
  };
  const onOver = (event: PointerEvent) => {
    if (event.pointerType !== "mouse") return;
    target = event.target instanceof Element ? event.target : null;
    resolve();
  };
  const onDown = (event: PointerEvent) => {
    if (event.pointerType !== "mouse") return;
    pressed = true;
    resolve();
  };
  const onUp = () => {
    pressed = false;
    resolve();
  };
  const onLeave = () => {
    shown = false;
    el.dataset.visible = "false";
  };
  const onEnter = () => {
    if (mx >= 0) {
      shown = true;
      el.dataset.visible = "true";
    }
  };
  const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes("Files");
  const onDrag = (event: DragEvent) => {
    if (!hasFiles(event)) return;
    dragging = true;
    mx = event.clientX;
    my = event.clientY;
    show();
    place();
    resolve();
  };
  const onDragEnd = () => {
    dragging = false;
    resolve();
  };
  const onDragLeave = (event: DragEvent) => {
    if (event.relatedTarget === null) onDragEnd();
  };

  window.addEventListener("pointermove", onMove, { passive: true });
  document.addEventListener("pointerover", onOver, { passive: true });
  window.addEventListener("pointerdown", onDown, { passive: true });
  window.addEventListener("pointerup", onUp, { passive: true });
  window.addEventListener("pointercancel", onUp, { passive: true });
  root.addEventListener("mouseleave", onLeave);
  root.addEventListener("mouseenter", onEnter);
  window.addEventListener("dragenter", onDrag);
  window.addEventListener("dragover", onDrag);
  window.addEventListener("dragleave", onDragLeave);
  window.addEventListener("drop", onDragEnd);
  window.addEventListener("dragend", onDragEnd);

  return () => {
    cancelAnimationFrame(raf);
    window.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerover", onOver);
    window.removeEventListener("pointerdown", onDown);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
    root.removeEventListener("mouseleave", onLeave);
    root.removeEventListener("mouseenter", onEnter);
    window.removeEventListener("dragenter", onDrag);
    window.removeEventListener("dragover", onDrag);
    window.removeEventListener("dragleave", onDragLeave);
    window.removeEventListener("drop", onDragEnd);
    window.removeEventListener("dragend", onDragEnd);
    root.classList.remove("has-cursor");
    el.remove();
  };
}
