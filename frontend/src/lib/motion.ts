/**
 * One shared set of springs and durations for Motion (motion/react). The same spring, sampled, is --ease-spring in
 * index.css, so CSS-driven press and hover states settle exactly like the Motion-driven layers. Only transform and
 * opacity are ever animated.
 */
export const spring = {
  /** Controls, presses, small layers. */
  snappy: { type: "spring", stiffness: 420, damping: 30, mass: 1 },
  /** Layout moves: the sliding thumb, the composer docking. */
  glide: { type: "spring", stiffness: 300, damping: 34, mass: 1 },
  /** Panels and sheets. */
  soft: { type: "spring", stiffness: 240, damping: 30, mass: 1 },
} as const;

/** Durations in seconds, mirrors --dur-* in index.css. */
export const dur = { fast: 0.12, base: 0.2, slow: 0.32 } as const;

/** A route change: a quick cross-fade with a small upward shift. */
export const pageEnter = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: dur.base, ease: [0.22, 1, 0.36, 1] },
} as const;

/** A floating layer growing out of its trigger (origin is set by the caller). */
export const layerEnter = {
  initial: { opacity: 0, scale: 0.96 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.97 },
  transition: spring.snappy,
} as const;

/** Stagger for lists on their first load only. */
export const staggerStep = 0.03;
