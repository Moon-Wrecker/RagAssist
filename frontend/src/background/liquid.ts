import { FRAGMENT, VERTEX } from "./liquid-shader";

/**
 * The liquid background: one fixed full-screen WebGL canvas behind the app, drawn by liquid-shader.ts.
 *
 * Performance and fallback rules (ADR 0016):
 * - rendered at half resolution (the canvas is scaled up by CSS), capped at 30 frames per second;
 * - paused while the tab is hidden, and no React work happens per frame: this module owns its own loop;
 * - without WebGL the static CSS version (.ambient) stays visible; with prefers-reduced-motion the shader draws a
 *   single still frame (and again on resize or theme change, never continuously).
 */
const RENDER_SCALE = 0.5;
const FRAME_MS = 1000 / 30;

function compile(gl: WebGLRenderingContext, type: number, source: string): WebGLShader | null {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

export interface LiquidHandle {
  /** Where the reading column is (centre x and half width, 0..1 of the window); pass it again when the layout changes. */
  setColumn(centre: number, halfWidth: number): void;
  destroy(): void;
}

export function startLiquid(): LiquidHandle | null {
  const root = document.documentElement;
  const canvas = document.createElement("canvas");
  canvas.id = "liquid";
  canvas.setAttribute("aria-hidden", "true");
  const gl = canvas.getContext("webgl", { alpha: false, antialias: false, depth: false, stencil: false, powerPreference: "low-power", preserveDrawingBuffer: false });
  if (!gl) return null;

  const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX);
  const fragment = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
  const program = gl.createProgram();
  if (!vertex || !fragment || !program) return null;
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
  gl.useProgram(program);

  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, "aPos");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

  const uniform = (name: string) => gl.getUniformLocation(program, name);
  const uRes = uniform("uRes");
  const uTime = uniform("uTime");
  const uMouse = uniform("uMouse");
  const uDark = uniform("uDark");
  const uColumn = uniform("uColumn");
  const uSeed = uniform("uSeed");

  document.body.prepend(canvas);
  root.classList.add("liquid-on");

  const reducedQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let width = 0;
  let height = 0;
  let raf = 0;
  let lastFrame = 0;
  let clock = 20; // an arbitrary start so the first still frame is not the noise origin
  let lastTick = 0;
  const mouse = { x: 0.5, y: 0.5, tx: 0.5, ty: 0.5 };
  let column = { centre: 0.5, half: 0.3 };
  let dark = root.dataset.theme === "dark";

  function resize() {
    const w = Math.max(2, Math.round(window.innerWidth * RENDER_SCALE));
    const h = Math.max(2, Math.round(window.innerHeight * RENDER_SCALE));
    if (w === width && h === height) return;
    width = w;
    height = h;
    canvas.width = w;
    canvas.height = h;
    gl!.viewport(0, 0, w, h);
    draw();
  }

  function draw() {
    gl!.uniform2f(uRes, width, height);
    gl!.uniform1f(uTime, clock);
    gl!.uniform2f(uMouse, mouse.x, mouse.y);
    gl!.uniform1f(uDark, dark ? 1 : 0);
    gl!.uniform2f(uColumn, column.centre, column.half);
    gl!.uniform1f(uSeed, (clock * 7.31) % 97);
    gl!.drawArrays(gl!.TRIANGLES, 0, 3);
  }

  function frame(now: number) {
    raf = requestAnimationFrame(frame);
    if (now - lastFrame < FRAME_MS - 1) return;
    const dt = Math.min(0.1, (now - (lastTick || now)) / 1000);
    lastTick = now;
    lastFrame = now;
    clock += dt;
    // The pointer is eased on the CPU: a gentle lean, not a chase.
    mouse.x += (mouse.tx - mouse.x) * 0.06;
    mouse.y += (mouse.ty - mouse.y) * 0.06;
    draw();
  }

  function running() {
    return !reducedQuery.matches && document.visibilityState === "visible";
  }
  function sync() {
    cancelAnimationFrame(raf);
    raf = 0;
    lastTick = 0;
    if (running()) raf = requestAnimationFrame(frame);
    else draw();
  }

  const onPointer = (event: PointerEvent) => {
    mouse.tx = event.clientX / window.innerWidth;
    mouse.ty = event.clientY / window.innerHeight;
  };
  const onTheme = () => {
    dark = root.dataset.theme === "dark";
    if (!raf) draw();
  };
  const themeObserver = new MutationObserver(onTheme);
  themeObserver.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  window.addEventListener("pointermove", onPointer, { passive: true });
  window.addEventListener("resize", resize, { passive: true });
  document.addEventListener("visibilitychange", sync);
  reducedQuery.addEventListener("change", sync);
  canvas.addEventListener("webglcontextlost", (event) => {
    event.preventDefault();
    cancelAnimationFrame(raf);
    root.classList.remove("liquid-on");
  });
  canvas.addEventListener("webglcontextrestored", () => {
    // Rebuilding every GL object is not worth it: reload-free recovery would need the whole setup again.
    root.classList.remove("liquid-on");
  });

  resize();
  sync();

  return {
    setColumn(centre, half) {
      column = { centre, half };
      if (!raf) draw();
    },
    destroy() {
      cancelAnimationFrame(raf);
      themeObserver.disconnect();
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", sync);
      reducedQuery.removeEventListener("change", sync);
      canvas.remove();
      root.classList.remove("liquid-on");
    },
  };
}
