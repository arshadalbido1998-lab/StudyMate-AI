import { useRef } from "react";
import { useScroll, useTransform, type MotionValue } from "framer-motion";

/**
 * Tracks scroll progress of a section relative to the viewport.
 * 0   -> section start enters the bottom of the viewport
 * 1   -> section end leaves the top of the viewport
 * Used to drive the "one continuous story" scroll animations
 * (documents becoming summaries, cards flipping, quiz resolving, etc.)
 */
export function useSectionProgress<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  return { ref, scrollYProgress };
}

export function clampedRange(
  value: MotionValue<number>,
  input: number[],
  output: number[]
) {
  return useTransform(value, input, output);
}
