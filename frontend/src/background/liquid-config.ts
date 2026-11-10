/**
 * The brightness budget of the liquid background, shared by the shader and by the contrast test so the readability
 * rule is checked against the same numbers the GPU draws. Values are sRGB grey levels (0 black, 1 white).
 *
 * Dark theme: the liquid stays between black and mid-grey. It is brightest toward the screen edges (`edge`) and held
 * much lower under the reading column (`scrim`). Light theme is the inverse (1 - value), so the dimmest areas of the
 * light theme sit at the edges.
 */
export const LIQUID = {
  /** Darkest ink (dark theme). */
  floor: 0.015,
  /** Brightest ink in the middle of the screen. */
  centre: 0.27,
  /** Brightest ink at the screen edges. */
  edge: 0.38,
  /** Brightest ink under the reading column (the soft dark scrim). */
  scrim: 0.17,
  /** Film grain amplitude added to the final grey (peak, either way). */
  grain: 0.016,
} as const;

/** The brightest grey the dark theme backdrop can reach, grain included (the worst case for light text). */
export const DARK_BACKDROP_MAX = LIQUID.edge + LIQUID.grain;
/** The dimmest grey the light theme backdrop can reach, grain included (the worst case for dark text). */
export const LIGHT_BACKDROP_MIN = 1 - DARK_BACKDROP_MAX;

/** The brightest grey the dark theme can reach under the reading column, where page text sits directly on the liquid. */
export const DARK_PAGE_MAX = LIQUID.scrim + LIQUID.grain;
/** The dimmest grey the light theme can reach under the reading column. */
export const LIGHT_PAGE_MIN = 1 - DARK_PAGE_MAX;
