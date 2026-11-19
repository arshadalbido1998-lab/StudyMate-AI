import { motion, useTransform } from "framer-motion";
import { useSectionProgress } from "../hooks/useSectionProgress";
import { stages } from "../data/pipeline";

const stage = stages[0];

export default function NotesSection() {
  const { ref, scrollYProgress } = useSectionProgress<HTMLDivElement>();
  const documentY = useTransform(scrollYProgress, [0, 0.24, 0.72, 1], [80, 0, -18, -80]);
  const documentRotate = useTransform(scrollYProgress, [0, 0.35, 0.8, 1], [-8, 0, 2, 8]);
  const documentScale = useTransform(scrollYProgress, [0, 0.25, 0.78, 1], [0.84, 1, 1.02, 0.82]);
  const scanY = useTransform(scrollYProgress, [0.22, 0.72], ["0%", "100%"]);
  const scanOpacity = useTransform(scrollYProgress, [0.16, 0.24, 0.78, 0.9], [0, 1, 1, 0]);
  const highlight = useTransform(scrollYProgress, [0.22, 0.6], ["0%", "100%"]);
  const pageLeft = useTransform(scrollYProgress, [0.4, 0.82], [0, -115]);
  const pageRight = useTransform(scrollYProgress, [0.4, 0.82], [0, 115]);
  const fragmentOpacity = useTransform(scrollYProgress, [0.48, 0.65, 0.9], [0, 1, 0.9]);
  const fragmentScale = useTransform(scrollYProgress, [0.48, 0.72], [0.7, 1]);
  const extractX = useTransform(scrollYProgress, [0.45, 0.82], [0, 80]);

  return (
    <section id="notes" ref={ref} className="relative min-h-[180vh]">
      <div className="sticky top-0 mx-auto flex min-h-screen w-full max-w-[94rem] flex-col justify-start overflow-hidden px-6 pb-8 pt-28 md:px-16 lg:justify-center lg:py-24 lg:pl-32">
        <div className="grid items-center gap-3 lg:grid-cols-[0.72fr_1.28fr] lg:gap-16">
          <div className="relative z-20">
            <motion.p style={{ opacity: useTransform(scrollYProgress, [0, 0.18, 0.9, 1], [0, 1, 1, 0]) }} className="text-xs font-bold uppercase tracking-[0.2em] text-electric">Stage {stage.index} · {stage.label}</motion.p>
            <h2 className="mt-4 max-w-xl font-display text-4xl font-semibold leading-[1.02] tracking-[-0.05em] text-ink sm:text-6xl">Drop in what you already have.</h2>
            <p className="mt-6 max-w-md text-base leading-relaxed text-inkSoft">{stage.description}</p>
            <div className="mt-8 flex items-center gap-3 text-xs font-bold uppercase tracking-[0.16em] text-inkSoft"><span className="grid h-8 w-8 place-items-center rounded-xl bg-electric text-white">01</span>Watch the page become a study system</div>
          </div>

          <div className="relative -mt-2 h-[25rem] [perspective:1400px] sm:h-[31rem] lg:mt-0 lg:h-[37rem]">
            <motion.div style={{ opacity: fragmentOpacity, scale: fragmentScale, x: pageLeft, rotate: -7 }} className="absolute left-[14%] top-[15%] z-10 hidden w-52 rounded-2xl border border-electric/20 bg-electric/[0.08] p-4 text-xs leading-relaxed text-ink sm:block">Processes share the CPU through time-slicing.</motion.div>
            <motion.div style={{ opacity: fragmentOpacity, scale: fragmentScale, x: pageRight, rotate: 7 }} className="absolute right-[10%] top-[28%] z-10 hidden w-52 rounded-2xl border border-coral/20 bg-coral/[0.09] p-4 text-xs leading-relaxed text-ink sm:block">The kernel mediates every hardware request.</motion.div>

            <motion.div style={{ y: documentY, rotate: documentRotate, scale: documentScale, transformOrigin: "50% 50%" }} className="absolute left-1/2 top-1/2 z-20 w-[min(88%,30rem)] -translate-x-1/2 -translate-y-1/2 rounded-[1.5rem] border border-white/90 bg-white/85 p-5 sm:p-7">
              <div className="flex items-center justify-between border-b border-ink/10 pb-4"><div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-coral/20 text-[0.6rem] font-bold text-coral">PDF</span><div><p className="text-xs font-bold text-ink">operating_systems_ch3.pdf</p><p className="mt-1 text-[0.55rem] text-inkSoft">Page 04 of 18 · imported just now</p></div></div><span className="rounded-full bg-mint/25 px-2.5 py-1 text-[0.55rem] font-bold text-ink">AI READY</span></div>
              <div className="relative mt-7 space-y-4 overflow-hidden rounded-xl bg-paper/70 p-5"><div className="h-2 w-2/5 rounded-full bg-ink/15" /><p className="font-display text-sm font-semibold text-ink sm:text-base">Chapter 03 / Operating Systems</p><p className="text-[0.65rem] leading-relaxed text-inkSoft">How computers coordinate processes, memory, and hardware.</p>{["An operating system manages hardware resources.", "Processes share the CPU through time-slicing.", "The kernel mediates every hardware request.", "Memory is allocated according to priority."].map((line, index) => <div key={line} className="relative flex items-start gap-3 text-[0.65rem] leading-relaxed text-inkSoft"><motion.span style={{ width: index === 1 || index === 2 ? highlight : "0%" }} className="absolute -inset-x-2 top-0 h-full rounded bg-electric/15" /><span className="relative mt-1 h-2 w-2 shrink-0 rounded-sm bg-electric/70" style={{ opacity: index === 3 ? 0.25 : 1 }} /><span className="relative">{line}</span></div>)}<motion.div style={{ y: scanY, opacity: scanOpacity }} className="pointer-events-none absolute inset-x-0 top-0 h-10 bg-gradient-to-b from-transparent via-electric/25 to-transparent " /></div>
              <div className="mt-5 flex items-center justify-between text-[0.6rem] font-bold text-electric"><span className="flex items-center gap-2"><span className="h-2 w-2 animate-pulse rounded-full bg-electric" />Scanning key concepts</span><span className="text-inkSoft">{stage.index}/05</span></div>
            </motion.div>
            <motion.div style={{ opacity: fragmentOpacity, x: extractX, y: 90 }} className="absolute bottom-[4%] left-[27%] z-30 rounded-full border border-white/80 bg-ink px-4 py-2 text-[0.58rem] font-bold uppercase tracking-widest text-paper ">extracting meaning</motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}
