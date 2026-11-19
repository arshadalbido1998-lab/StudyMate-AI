import { useEffect, useState } from "react";
import { motion, useTransform, animate } from "framer-motion";
import { useSectionProgress } from "../hooks/useSectionProgress";
import { stages } from "../data/pipeline";

const stage = stages[4];
const stats = [
  { label: "Study time", value: 0, suffix: " hrs" },
  { label: "Completed tasks", value: 0, suffix: "" },
  { label: "Quizzes completed", value: 0, suffix: "" },
  { label: "Average score", value: 0, suffix: "%" },
  { label: "Notes uploaded", value: 0, suffix: "" },
  { label: "Study streak", value: 0, suffix: " days" },
];

function Counter({ to, suffix = "" }: { to: number; suffix?: string }) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    const controls = animate(0, to, { duration: 1.1, ease: [0.22, 1, 0.36, 1], onUpdate: (current) => setValue(Math.round(current)) });
    return () => controls.stop();
  }, [to]);
  return <span>{value}{suffix}</span>;
}

export default function MasterSection() {
  const { ref, scrollYProgress } = useSectionProgress<HTMLDivElement>();
  const convergence = useTransform(scrollYProgress, [0.08, 0.62], [0, 1]);
  const ringScale = useTransform(scrollYProgress, [0.2, 0.68], [0.65, 1]);
  const titleY = useTransform(scrollYProgress, [0.35, 0.72], [40, 0]);
  const panelOpacity = useTransform(scrollYProgress, [0.42, 0.7, 1], [0, 1, 0.8]);
  const lineLength = useTransform(scrollYProgress, [0.15, 0.6], [0, 1]);

  return (
    <section id="master" ref={ref} className="relative min-h-[175vh]">
      <div className="sticky top-0 mx-auto flex min-h-screen w-full max-w-[94rem] flex-col justify-center overflow-hidden px-6 py-24 md:px-16 lg:pl-32">
        <motion.div style={{ opacity: useTransform(scrollYProgress, [0, 0.18, 0.9, 1], [0, 1, 1, 0]) }} className="relative z-20 max-w-xl">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-violet">Stage {stage.index} · {stage.label}</p>
          <motion.h2 style={{ y: titleY }} className="mt-4 font-display text-4xl font-semibold leading-[1.02] tracking-[-0.05em] text-ink sm:text-6xl">Master your subject.</motion.h2>
          <p className="mt-6 max-w-md text-base leading-relaxed text-inkSoft">{stage.description}</p>
        </motion.div>

        <div className="relative mt-6 grid items-center gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:gap-20">
          <div className="relative h-[27rem] sm:h-[32rem]">
            <motion.div style={{ scale: ringScale, opacity: convergence }} className="absolute left-1/2 top-1/2 h-64 w-64 -translate-x-1/2 -translate-y-1/2 rounded-full border border-electric/20 bg-electric/[0.04] sm:h-80 sm:w-80" />
            <motion.div style={{ scale: ringScale, rotate: useTransform(scrollYProgress, [0.15, 0.7], [0, 180]), opacity: convergence }} className="absolute left-1/2 top-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full border border-dashed border-violet/25 sm:h-96 sm:w-96" />
            {[
              { label: "PDF", className: "left-[10%] top-[18%] bg-coral/20 text-coral", x: -80, y: -60 },
              { label: "MAP", className: "right-[8%] top-[20%] bg-violet/15 text-violet", x: 80, y: -50 },
              { label: "CARD", className: "bottom-[17%] left-[14%] bg-mint/30 text-ink", x: -70, y: 55 },
              { label: "QUIZ", className: "bottom-[13%] right-[12%] bg-sky/25 text-ink", x: 70, y: 50 },
            ].map((object) => <motion.span key={object.label} style={{ opacity: convergence, x: useTransform(scrollYProgress, [0.12, 0.68], [object.x, 0]), y: useTransform(scrollYProgress, [0.12, 0.68], [object.y, 0]), scale: useTransform(scrollYProgress, [0.12, 0.68], [0.8, 1]) }} className={`absolute rounded-full border border-white/80 px-3 py-2 text-[0.55rem] font-bold tracking-widest ${object.className}`}>{object.label}</motion.span>)}
            <motion.div style={{ scale: ringScale, opacity: convergence }} className="absolute left-1/2 top-1/2 grid h-24 w-24 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-[1.7rem] bg-ink font-display text-center text-xs font-semibold leading-tight text-paper sm:h-28 sm:w-28">Your<br />learning<br />system</motion.div>
          </div>

          <motion.div style={{ opacity: panelOpacity }} className="relative z-20 rounded-[1.6rem] border border-white/90 bg-white/75 p-6 sm:p-8">
            <div className="flex items-center justify-between"><p className="text-xs font-bold uppercase tracking-[0.15em] text-inkSoft">Overall progress</p><span className="rounded-full bg-violet/10 px-3 py-1 text-[0.6rem] font-bold text-violet">NEW JOURNEY</span></div>
            <p className="mt-3 font-display text-4xl font-semibold text-ink"><Counter to={0} suffix="%" /></p>
            <svg viewBox="0 0 200 60" className="mt-4 h-16 w-full"><motion.polyline points="0,50 40,50 80,50 120,50 160,50 200,50" fill="none" stroke="#FFFFFF" strokeWidth="2.5" strokeLinecap="round" style={{ pathLength: lineLength }} /></svg>
            <div className="mt-6 grid grid-cols-2 gap-x-4 gap-y-5 border-t border-ink/10 pt-5 sm:grid-cols-3">{stats.map((stat) => <div key={stat.label}><p className="font-display text-xl font-semibold text-ink"><Counter to={stat.value} suffix={stat.suffix} /></p><p className="text-xs text-inkSoft">{stat.label}</p></div>)}</div>
            <div className="mt-7 rounded-xl border border-violet/15 bg-violet/[0.06] px-4 py-3 text-sm text-inkSoft">No study activity yet.<br /><span className="text-ink">Your learning journey starts here.</span></div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
