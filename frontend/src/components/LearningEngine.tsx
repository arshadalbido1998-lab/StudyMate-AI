import { useState, type RefObject } from "react";
import { motion, useScroll, useSpring, useTransform } from "framer-motion";
import { correctOptionId, sampleQuestion } from "../data/quiz";
import { stages } from "../data/pipeline";

const concepts = [
  { label: "Process", x: 21, y: 29, color: "#FFFFFF" },
  { label: "Kernel", x: 55, y: 16, color: "#FFFFFF" },
  { label: "Memory", x: 29, y: 70, color: "#FFFFFF" },
  { label: "Scheduling", x: 73, y: 52, color: "#FFFFFF" },
  { label: "File system", x: 79, y: 79, color: "#FFFFFF" },
];
const links: [number, number][] = [[0, 1], [0, 2], [1, 3], [2, 3], [3, 4]];

function StageWord({ label, index, progress }: { label: string; index: number; progress: ReturnType<typeof useSpring> }) {
  const start = index * 0.2;
  const active = useTransform(progress, [start, start + 0.12, start + 0.2], [0.35, 1, 0.55]);
  const x = useTransform(progress, [start, start + 0.2], [index % 2 ? 18 : -18, 0]);
  return <motion.div style={{ opacity: active, x }} className="flex items-center gap-2 text-[0.57rem] font-bold uppercase tracking-[0.18em] text-inkSoft"><span className="grid h-6 w-6 place-items-center rounded-full border border-ink/15 text-[0.5rem] text-ink">0{index + 1}</span>{label}</motion.div>;
}

export default function LearningEngine({ containerRef }: { containerRef: RefObject<HTMLDivElement> }) {
  const { scrollYProgress } = useScroll({ target: containerRef, offset: ["start start", "end end"] });
  const progress = useSpring(scrollYProgress, { stiffness: 90, damping: 26, restDelta: 0.001 });
  const [selected, setSelected] = useState<string | null>(null);
  const [flipped, setFlipped] = useState(false);

  const phase = useTransform(progress, [0, 0.19, 0.39, 0.59, 0.79, 1], [0, 1, 2, 3, 4, 5]);
  const engineScale = useTransform(progress, [0, 0.12, 0.5, 0.92, 1], [0.82, 1, 1.05, 1, 0.94]);
  const engineY = useTransform(progress, [0, 0.5, 1], [70, 0, -24]);
  const engineRotate = useTransform(progress, [0, 0.28, 0.66, 1], [-4, 0, 1, 5]);
  const engineOpacity = useTransform(progress, [0, 0.08, 0.92, 1], [0, 1, 1, 1]);
  const stageWordY = useTransform(progress, [0, 1], [100, -100]);

  const documentOpacity = useTransform(progress, [0.02, 0.12, 0.28, 0.42], [1, 1, 0.75, 0]);
  const documentScale = useTransform(progress, [0, 0.18, 0.4], [0.78, 1, 0.5]);
  const documentRotate = useTransform(progress, [0, 0.35, 0.46], [-8, 0, 16]);
  const documentX = useTransform(progress, [0, 0.3, 0.48], [-70, 0, -150]);
  const scanX = useTransform(progress, [0.08, 0.3], ["-110%", "110%"]);
  const scanOpacity = useTransform(progress, [0.06, 0.1, 0.32, 0.38], [0, 1, 1, 0]);
  const highlight = useTransform(progress, [0.12, 0.34], ["0%", "100%"]);

  const graphOpacity = useTransform(progress, [0.27, 0.42, 0.75, 0.9], [0, 1, 1, 0.1]);
  const graphScale = useTransform(progress, [0.28, 0.52, 0.8], [0.45, 1, 0.65]);
  const graphRotate = useTransform(progress, [0.3, 0.7, 0.86], [-12, 0, 18]);
  const graphX = useTransform(progress, [0.32, 0.54, 0.8], [130, 0, -120]);
  const cardOpacity = useTransform(progress, [0.49, 0.62, 0.88, 0.96], [0, 1, 1, 0]);
  const cardSpread = useTransform(progress, [0.5, 0.7, 0.86], [0, 1, 0.35]);
  const quizOpacity = useTransform(progress, [0.69, 0.8, 0.98], [0, 1, 0.15]);
  const quizScale = useTransform(progress, [0.67, 0.82, 1], [0.72, 1, 0.76]);
  const quizPointerEvents = useTransform(progress, [0.68, 0.74, 0.98, 1], ["none", "auto", "auto", "none"]);
  const masterOpacity = useTransform(progress, [0.83, 0.94, 1], [0, 1, 1]);
  const convergence = useTransform(progress, [0.84, 1], [0, 1]);

  return (
    <section ref={containerRef} className="relative min-h-[520vh]" aria-label="StudyMate learning journey">
      <div className="sticky top-0 flex min-h-screen items-center overflow-hidden px-5 py-24 md:px-12 lg:px-24">
        <motion.div style={{ opacity: engineOpacity, scale: engineScale, y: engineY, rotate: engineRotate }} className="relative mx-auto w-full max-w-[98rem] [perspective:1800px]">
          <div className="absolute -inset-24 rounded-[4rem] bg-black blur-3xl" />

          <div className="relative grid items-center gap-10 lg:grid-cols-[0.48fr_1.52fr] lg:gap-16">
            <div className="relative z-40 hidden space-y-5 lg:block">
              <motion.div style={{ y: stageWordY }} className="space-y-5"><StageWord label="Notes" index={0} progress={progress} /><StageWord label="Understand" index={1} progress={progress} /><StageWord label="Remember" index={2} progress={progress} /><StageWord label="Practice" index={3} progress={progress} /><StageWord label="Master" index={4} progress={progress} /></motion.div>
              <div className="mt-10 max-w-[13rem] border-t border-ink/10 pt-4 text-[0.62rem] leading-relaxed text-inkSoft">Scroll to move through the learning engine.</div>
            </div>

            <div className="relative h-[35rem] sm:h-[42rem] [transform-style:preserve-3d]">
              <motion.div style={{ opacity: documentOpacity, scale: documentScale, x: documentX, rotate: documentRotate }} className="absolute left-1/2 top-1/2 z-20 w-[min(88%,31rem)] -translate-x-1/2 -translate-y-1/2 rounded-[1.7rem] border border-white/90 bg-white/88 p-5 sm:p-7">
                <div className="flex items-center justify-between border-b border-ink/10 pb-4"><div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-coral/20 text-[0.6rem] font-bold text-coral">PDF</span><div><p className="text-xs font-bold text-ink">operating_systems_ch3.pdf</p><p className="mt-1 text-[0.55rem] text-inkSoft">Page 04 of 18</p></div></div><span className="rounded-full bg-mint/25 px-2.5 py-1 text-[0.55rem] font-bold text-ink">AI READY</span></div>
                <div className="relative mt-6 overflow-hidden rounded-xl bg-paper/80 p-5"><div className="h-2 w-2/5 rounded bg-ink/15" /><p className="mt-5 font-display text-sm font-semibold text-ink sm:text-base">Chapter 03 / Operating Systems</p><p className="mt-2 text-[0.65rem] leading-relaxed text-inkSoft">How computers coordinate processes, memory, and hardware.</p><div className="mt-6 space-y-4">{["An operating system manages hardware resources.", "Processes share the CPU through time-slicing.", "The kernel mediates every hardware request.", "Memory is allocated according to priority."].map((line, index) => <div key={line} className="relative flex items-start gap-3 text-[0.62rem] leading-relaxed text-inkSoft"><motion.span style={{ width: index === 1 || index === 2 ? highlight : "0%" }} className="absolute -inset-x-2 top-0 h-full rounded bg-electric/15" /><span className="relative mt-1 h-2 w-2 shrink-0 rounded-sm bg-electric/70" style={{ opacity: index === 3 ? 0.25 : 1 }} /><span className="relative">{line}</span></div>)}</div><motion.div style={{ x: scanX, opacity: scanOpacity }} className="pointer-events-none absolute inset-y-0 left-0 w-12 bg-gradient-to-r from-transparent via-electric/40 to-transparent " /></div>
                <div className="mt-5 flex items-center justify-between text-[0.58rem] font-bold text-electric"><span className="flex items-center gap-2"><span className="h-2 w-2 animate-pulse rounded-full bg-electric" />AI scan active</span><span className="text-inkSoft">01 / 05</span></div>
              </motion.div>

              <motion.div style={{ opacity: graphOpacity, scale: graphScale, rotate: graphRotate, x: graphX }} className="absolute inset-[3%] z-30 rounded-[2.8rem] border border-violet/20 bg-violet/[0.035] ">
                <svg viewBox="0 0 100 100" className="absolute inset-[8%] h-[84%] w-[84%] overflow-visible">{links.map(([from, to], index) => <motion.line key={`${from}-${to}`} x1={concepts[from].x} y1={concepts[from].y} x2={concepts[to].x} y2={concepts[to].y} stroke="#FFFFFF" strokeWidth="0.7" strokeDasharray="2 2" style={{ pathLength: useTransform(progress, [0.27 + index * 0.04, 0.48 + index * 0.04], [0, 1]) }} />)}{concepts.map((concept, index) => <motion.circle key={concept.label} cx={concept.x} cy={concept.y} r={index === 1 ? 5 : 4} fill={concept.color} style={{ scale: useTransform(progress, [0.27 + index * 0.05, 0.43 + index * 0.05], [0, 1]), x: useTransform(progress, [0.3, 0.58], [index % 2 ? 14 : -14, 0]) }} />)}</svg>{concepts.map((concept, index) => <motion.span key={concept.label} style={{ left: `${concept.x + 8}%`, top: `${concept.y + 8}%`, opacity: useTransform(progress, [0.33 + index * 0.05, 0.48 + index * 0.05], [0, 1]) }} className="absolute -translate-x-1/2 translate-y-3 whitespace-nowrap rounded-full border border-white/80 bg-white/80 px-2.5 py-1.5 text-[0.58rem] font-bold text-ink ">{concept.label}</motion.span>)}</motion.div>

              <div className="absolute inset-0 z-40 pointer-events-none">
                {[0, 1, 2].map((index) => { const x = useTransform(cardSpread, [0, 1], [index * 13 - 13, (index - 1) * 195]); const y = useTransform(cardSpread, [0, 1], [index * -7, index === 1 ? -13 : 30]); const rotate = useTransform(cardSpread, [0, 1], [index === 1 ? 0 : index === 0 ? -4 : 4, index === 1 ? 0 : index === 0 ? -8 : 8]); return <motion.button key={index} onClick={() => setFlipped(!flipped)} style={{ opacity: cardOpacity, x, y, rotate, zIndex: 50 - index }} className="pointer-events-auto absolute left-1/2 top-1/2 h-60 w-48 -translate-x-1/2 -translate-y-1/2 [perspective:1200px] sm:h-72 sm:w-56" aria-label={`Flip learning flashcard ${index + 1}`}><motion.div animate={{ rotateY: flipped && index === 1 ? 180 : 0 }} className="relative h-full w-full [transform-style:preserve-3d]"><div className="absolute inset-0 flex flex-col justify-between rounded-[1.4rem] border border-white/80 bg-mint/95 p-5 text-left [backface-visibility:hidden]"><span className="text-[0.58rem] font-bold uppercase tracking-widest text-ink/50">03 / Remember</span><span className="font-display text-lg font-semibold leading-snug text-ink">{index === 1 ? "What is polymorphism?" : index === 0 ? "What is a kernel?" : "What is memory?"}</span><span className="text-[0.58rem] font-semibold text-ink/50">Click to flip</span></div><div className="absolute inset-0 flex items-center rounded-[1.4rem] bg-ink p-6 text-left text-paper [backface-visibility:hidden] [transform:rotateY(180deg)]"><p className="text-sm leading-relaxed">{index === 1 ? "One interface, many implementations - a call behaves differently depending on the object." : "A core idea extracted from your study material."}</p></div></motion.div></motion.button>; })}
              </div>

              <motion.div style={{ opacity: quizOpacity, scale: quizScale, pointerEvents: quizPointerEvents }} className="absolute left-1/2 top-1/2 z-[60] w-[min(90%,31rem)] -translate-x-1/2 -translate-y-1/2 rounded-[1.7rem] border border-white/90 bg-white/90 p-6 sm:p-8"><div className="flex items-center justify-between border-b border-ink/10 pb-4"><span className="text-xs font-bold uppercase tracking-widest text-coral">Quiz 03 / 08</span><span className="text-xs font-semibold text-inkSoft">Practice</span></div><div className="mt-5 h-1.5 overflow-hidden rounded-full bg-ink/10"><motion.div style={{ width: useTransform(progress, [0.7, 0.9], ["0%", "37.5%"]) }} className="h-full rounded-full bg-coral" /></div><p className="mt-7 font-display text-xl font-semibold leading-snug text-ink">{sampleQuestion.question}</p><div className="mt-5 space-y-2">{sampleQuestion.options.map((option) => { const correct = option.id === correctOptionId; const chosen = selected === option.id; return <button key={option.id} disabled={selected !== null} onClick={() => setSelected(option.id)} className={["w-full rounded-xl border px-4 py-3 text-left text-sm transition-all", selected === null ? "border-ink/10 hover:-translate-y-0.5 hover:border-coral/50" : correct ? "border-mint bg-mint/20" : chosen ? "border-coral bg-coral/10" : "border-ink/10 opacity-50"].join(" ")}>{option.text}</button>; })}</div>{selected && <p className="mt-4 text-sm font-semibold text-ink">{selected === correctOptionId ? "Correct - the concept is sticking." : "Not quite - send this one back to review."}</p>}</motion.div>

              <motion.div style={{ opacity: masterOpacity, pointerEvents: "none" }} className="absolute inset-0 z-[70] grid place-items-center"><div className="relative grid h-72 w-72 place-items-center rounded-full border-2 border-electric/35 bg-electric/[0.1] sm:h-[22rem] sm:w-[22rem]"><motion.div style={{ scale: convergence, rotate: useTransform(progress, [0.84, 1], [0, 180]) }} className="absolute inset-5 rounded-full border border-dashed border-violet/45" /><div className="relative rounded-2xl bg-ink px-6 py-5 text-center font-display text-lg font-semibold leading-tight text-paper ">MASTER<br />YOUR<br />SUBJECT.</div></div></motion.div>
            </div>
          </div>

          <motion.div style={{ opacity: useTransform(progress, [0, 0.08, 0.92, 1], [1, 0, 0, 1]) }} className="mt-2 text-center text-[0.58rem] font-bold uppercase tracking-[0.22em] text-inkSoft lg:hidden">Scroll through the engine · Notes → Understand → Remember → Practice → Master</motion.div>
          <motion.div style={{ opacity: masterOpacity, pointerEvents: "none" }} className="relative z-40 mt-7 rounded-2xl border border-white/90 bg-white p-4 lg:absolute lg:bottom-0 lg:right-4 lg:w-80"><p className="text-xs font-bold uppercase tracking-widest text-inkSoft">New learner state</p><div className="mt-3 grid grid-cols-2 gap-3 text-xs text-inkSoft"><span>Study time <strong className="block text-ink">0 hrs</strong></span><span>Completed tasks <strong className="block text-ink">0</strong></span><span>Quizzes completed <strong className="block text-ink">0</strong></span><span>Average score <strong className="block text-ink">0%</strong></span><span>Notes uploaded <strong className="block text-ink">0</strong></span><span>Study streak <strong className="block text-ink">0 days</strong></span><span>Overall progress <strong className="block text-ink">0%</strong></span></div></motion.div>
        </motion.div>
      </div>
    </section>
  );
}
