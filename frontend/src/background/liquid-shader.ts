import { LIQUID } from "./liquid-config";

/**
 * Ink in water: domain-warped fractal noise (Inigo Quilez, "warping", https://iquilezles.org/articles/warp/) turned
 * into soft black and white shapes that merge and split, plus film grain. One fragment shader, no textures.
 * The grey level is bounded by LIQUID (liquid-config.ts), which the contrast test reads.
 */
export const VERTEX = /* glsl */ `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

export const FRAGMENT = /* glsl */ `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform vec2 uRes;      // canvas size in pixels
uniform float uTime;    // seconds
uniform vec2 uMouse;    // 0..1, origin top-left, smoothed on the CPU
uniform float uDark;    // 1 dark theme, 0 light theme
uniform vec2 uColumn;   // reading column: centre x and half width, both 0..1
uniform float uSeed;    // changes grain every frame

const float FLOOR = ${LIQUID.floor.toFixed(4)};
const float CENTRE = ${LIQUID.centre.toFixed(4)};
const float EDGE = ${LIQUID.edge.toFixed(4)};
const float SCRIM = ${LIQUID.scrim.toFixed(4)};
const float GRAIN = ${LIQUID.grain.toFixed(4)};

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  mat2 r = mat2(0.8, -0.6, 0.6, 0.8);
  for (int i = 0; i < 4; i++) {
    v += a * noise(p);
    p = r * p * 2.03 + 11.7;
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  uv.y = 1.0 - uv.y;
  float aspect = uRes.x / uRes.y;
  vec2 p = vec2(uv.x * aspect, uv.y) * 1.6;

  // The liquid leans very slightly toward the pointer.
  vec2 toMouse = vec2((uMouse.x - uv.x) * aspect, uMouse.y - uv.y);
  float pull = exp(-dot(toMouse, toMouse) * 3.0);
  p += toMouse * pull * 0.22;

  float t = uTime * 0.045;
  vec2 q = vec2(fbm(p + vec2(0.0, t)), fbm(p + vec2(5.2, 1.3) - t));
  vec2 r = vec2(fbm(p + 3.6 * q + vec2(1.7, 9.2) + t * 1.3), fbm(p + 3.6 * q + vec2(8.3, 2.8) - t));
  float f = fbm(p + 3.2 * r);

  // Soft threshold: shapes with wide soft edges, so they read as ink, not as noise.
  float ink = smoothstep(0.32, 0.72, f + 0.35 * (r.x - 0.5));

  // How far this pixel is from the middle of the screen: brighter ink is allowed toward the edges.
  vec2 d = (uv - 0.5) * vec2(1.0, 1.15);
  float edge = smoothstep(0.18, 0.62, length(d));
  float hi = mix(CENTRE, EDGE, edge);

  // A soft dark scrim under the reading column.
  float col = 1.0 - smoothstep(uColumn.y * 0.55, uColumn.y * 1.25, abs(uv.x - uColumn.x));
  hi = mix(hi, SCRIM, col * (1.0 - edge * 0.6));

  float lum = mix(FLOOR, hi, ink);
  // Light theme is the inverse of the dark one.
  lum = mix(1.0 - lum, lum, uDark);

  float g = (hash(gl_FragCoord.xy + uSeed) - 0.5) * 2.0 * GRAIN;
  lum = clamp(lum + g, 0.0, 1.0);
  gl_FragColor = vec4(vec3(lum), 1.0);
}
`;
