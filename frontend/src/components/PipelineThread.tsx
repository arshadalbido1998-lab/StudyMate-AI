import type { RefObject } from "react";
import { motion, useScroll, useSpring } from "framer-motion";
import { stages } from "../data/pipeline";

const colorMap: Record<string, string> = {
  electric: "#FFFFFF",
  violet: "#FFFFFF",
  mint: "#FFFFFF",
  coral: "#FFFFFF",
  lavender: "#FFFFFF",
};

/**
 * A fixed vertical line running down the left margin from the Notes
 * section to Master. Fill height tracks overall scroll progress through
 * the story container, and each stage gets a dot that lights up as the
 * thread passes it. This is the single connective device that makes the
 * five sections read as one pipeline instead of five separate blocks.
 */
export default function PipelineThread({
  containerRef,
}: {
  containerRef: RefObject<HTMLElement>;
}) {
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start center", "end center"],
  });
  const fill = useSpring(scrollYProgress, { stiffness: 90, damping: 24 });

  return (
    <div className="pointer-events-none absolute left-6 top-0 hidden h-full w-px lg:block xl:left-12">
      <div className="sticky top-0 h-screen">
        <div className="absolute left-0 top-[10%] h-[80%] w-px bg-ink/10" />
        <motion.div
          className="absolute left-0 top-[10%] w-px origin-top bg-gradient-to-b from-electric via-violet to-lavender"
          style={{ scaleY: fill, height: "80%" }}
        />
        {stages.map((stage, i) => (
          <div
            key={stage.id}
            className="absolute left-0 flex -translate-x-1/2 -translate-y-1/2 items-center"
            style={{ top: `${10 + (i / (stages.length - 1)) * 80}%` }}
          >
            <span
              className="block h-3 w-3 rounded-full border-2 border-paper "
              style={{ backgroundColor: colorMap[stage.color] }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
