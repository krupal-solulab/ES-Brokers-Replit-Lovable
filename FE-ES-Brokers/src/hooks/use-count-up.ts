import { useEffect, useState } from "react";

/**
 * Animates 0 → target once `start` flips true (pair with useInView). Skips
 * straight to `target` if the tab is backgrounded on mount or reduced-motion
 * already made useInView resolve synchronously — either way the number is
 * still correct, just not animated.
 */
export function useCountUp(target: number, start: boolean, durationMs = 900) {
  const [value, setValue] = useState(start ? target : 0);

  useEffect(() => {
    if (!start) return;
    if (
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      setValue(target);
      return;
    }
    let raf = 0;
    const startedAt = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(target * eased));
      if (progress < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [start, target, durationMs]);

  return value;
}
