import { motion, useTransform } from "framer-motion";
import { useSectionProgress } from "../hooks/useSectionProgress";
import { stages } from "../data/pipeline";

const stage = stages[1];
const nodes = [
  { label: "Process", x: 18, y: 32, color: "#FFFFFF", depth: -18 },
  { label: "Kernel", x: 53, y: 18, color: "#FFFFFF", depth: 12 },
  { label: "Scheduling", x: 72, y: 53, color: "#FFFFFF", depth: -8 },
  { label: "Memory", x: 28, y: 70, color: "#FFFFFF", depth: 15 },
  { label: "File system", x: 79, y: 79, color: "#FFFFFF", depth: 5 },
];
const edges: [number, number][] = [[0, 1], [0, 2], [1, 2], [2, 3], [2, 4], [3, 4]];

export default function UnderstandSection() {
  const { ref, scrollYProgress } = useSectionProgress<HTMLDivElement>();
  const graphOpacity = useTransform(scrollYProgress, [0, 0.16, 0.92, 1], [0, 1, 1, 0.2]);
  const graphScale = useTransform(scrollYProgress, [0, 0.38, 0.82, 1], [0.7, 1, 1.06, 0.88]);
  const graphRotate = useTransform(scrollYProgress, [0.2, 0.7, 1], [-8, 0, 7]);
  const mapX = useTransform(scrollYProgress, [0.12, 0.8], [100, 0]);
  const documentOpacity = useTransform(scrollYProgress, [0, 0.28, 0.52], [0.5, 0.26, 0]);
  const summaryOpacity = useTransform(scrollYProgress, [0.4, 0.62, 0.9], [0, 1, 1]);

  return (
    <section id="understand" ref={ref} className="relative min-h-[180vh]">
      <div className="sticky top-0 mx-auto flex min-h-screen w-full max-w-[94rem] flex-col justify-center overflow-hidden px-6 py-24 md:px-16 lg:pl-32">
        <div className="grid items-center gap-10 lg:grid-cols-[0.7fr_1.3fr] lg:gap-12">
          <div className="relative z-20">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-violet">Stage {stage.index} · {stage.label}</p>
            <h2 className="mt-4 max-w-xl font-display text-4xl font-semibold leading-[1.02] tracking-[-0.05em] text-ink sm:text-6xl">See the shape of the material.</h2>
            <p className="mt-6 max-w-md text-base leading-relaxed text-inkSoft">{stage.description}</p>
            <motion.div style={{ opacity: summaryOpacity, x: useTransform(scrollYProgress, [0.4, 0.68], [-18, 0]) }} className="mt-8 max-w-md rounded-2xl border border-white/80 bg-white/65 p-5 text-sm leading-relaxed text-ink "><span className="font-bold text-violet">AI summary - </span>An OS manages hardware on behalf of programs: it schedules the CPU across processes, mediates memory, and exposes a stable interface through the kernel.</motion.div>
          </div>

          <div className="relative h-[32rem] [perspective:1200px] sm:h-[38rem]">
            <motion.div style={{ opacity: documentOpacity, rotate: -8, x: useTransform(scrollYProgress, [0, 0.5], [0, -160]), scale: 0.86 }} className="absolute left-[17%] top-[18%] z-10 w-64 rounded-2xl border border-white/80 bg-white/65 p-5 "><div className="h-2 w-2/3 rounded bg-ink/10" /><div className="mt-5 space-y-3">{[1, 2, 3, 4, 5].map((line) => <div key={line} className="h-2 rounded bg-ink/[0.08]" />)}</div></motion.div>
            <motion.div style={{ opacity: graphOpacity, scale: graphScale, rotate: graphRotate, x: mapX, transformOrigin: "50% 50%" }} className="absolute inset-[4%] rounded-[2.5rem] border border-violet/15 bg-violet/[0.035] ">
              <svg viewBox="0 0 100 100" className="absolute inset-[8%] h-[84%] w-[84%] overflow-visible">
                {edges.map(([from, to], index) => <motion.line key={`${from}-${to}`} x1={nodes[from].x} y1={nodes[from].y} x2={nodes[to].x} y2={nodes[to].y} stroke="#FFFFFF" strokeWidth="0.65" strokeDasharray="2 2" style={{ pathLength: useTransform(scrollYProgress, [0.18 + index * 0.06, 0.58 + index * 0.05], [0, 1]) }} />)}
                {nodes.map((node, index) => <motion.circle key={node.label} cx={node.x} cy={node.y} r={index === 1 ? 5 : 4} fill={node.color} style={{ scale: useTransform(scrollYProgress, [0.2 + index * 0.07, 0.45 + index * 0.07], [0, 1]), x: useTransform(scrollYProgress, [0.2, 0.8], [node.depth, 0]) }} />)}
              </svg>
              {nodes.map((node, index) => <motion.span key={node.label} style={{ left: `${node.x + 8}%`, top: `${node.y + 8}%`, opacity: useTransform(scrollYProgress, [0.27 + index * 0.06, 0.48 + index * 0.06], [0, 1]), x: useTransform(scrollYProgress, [0.25, 0.8], [node.depth, 0]) }} className="absolute -translate-x-1/2 translate-y-3 whitespace-nowrap rounded-full border border-white/80 bg-white/80 px-2.5 py-1.5 text-[0.58rem] font-bold text-ink ">{node.label}</motion.span>)}
              <motion.div style={{ opacity: useTransform(scrollYProgress, [0.55, 0.8], [0, 1]) }} className="absolute left-[42%] top-[43%] rounded-full bg-electric px-3 py-1.5 text-[0.55rem] font-bold uppercase tracking-widest text-white ">core idea</motion.div>
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: 0.4 }} className="absolute bottom-0 right-0 z-30 w-56 rounded-2xl rounded-br-sm bg-ink p-4 text-xs leading-relaxed text-paper "><div className="mb-2 flex items-center gap-2 text-[0.55rem] font-bold uppercase tracking-widest text-mint"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-mint" />AI tutor</div>Think of the CPU like a teacher deciding who gets to speak next.</motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}
