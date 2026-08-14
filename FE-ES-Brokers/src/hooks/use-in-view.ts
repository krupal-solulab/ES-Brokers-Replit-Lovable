import { useEffect, useRef, useState, type RefObject } from "react";

function prefersReducedMotion() {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Fires once a ref enters the viewport (IntersectionObserver-based). Returns
 * `true` immediately, before observing, when the user has reduced motion set
 * — every caller (Reveal, use-count-up) treats "in view" as its cue to run an
 * animation, so this makes reduced-motion a no-op at the source instead of
 * needing a branch in every consumer.
 */
export function useInView<T extends Element>(
  options: IntersectionObserverInit = { threshold: 0.15 },
): [RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(prefersReducedMotion);

  useEffect(() => {
    if (inView) return;
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setInView(true);
        observer.disconnect();
      }
    }, options);
    observer.observe(el);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView]);

  return [ref, inView];
}
