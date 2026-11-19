import { useState } from "react";
import { motion, useTransform, type MotionValue } from "framer-motion";
import { useSectionProgress } from "../hooks/useSectionProgress";
import { stages } from "../data/pipeline";

const stage = stages[2];
const cards = [
  { front: "What is polymorphism?", back: "One interface, many implementations - a call behaves differently depending on the object." },
  { front: "What is encapsulation?", back: "Bundling data and the methods that operate on it, hiding internal state from outside code." },
  { front: "What is inheritance?", back: "A class acquiring properties and behavior from a parent class." },
];

function Flashcard({ front, back, index, spread }: { front: string; back: string; index: number; spread: MotionValue<number> }) {
  const [flipped, setFlipped] = useState(false);
  const x = useTransform(spread, [0, 1], [index * 18 - 18, (index - 1) * 230]);
  const y = useTransform(spread, [0, 1], [index * -8, index === 1 ? -16 : index === 0 ? 28 : 38]);
  const rotate = useTransform(spread, [0, 1], [index === 1 ? 0 : index === 0 ? -4 : 4, index === 1 ? 0 : index === 0 ? -8 : 8]);

  return (
    <motion.button onClick={() => setFlipped((value) => !value)} style={{ x, y, rotate, zIndex: cards.length - index }} whileHover={{ y: -26, scale: 1.025, rotateZ: 0 }} className="absolute left-1/2 top-1/2 h-60 w-48 -translate-x-1/2 -translate-y-1/2 [perspective:1200px] sm:h-72 sm:w-56" aria-label={`Flip flashcard: ${front}`}>
      <motion.div animate={{ rotateY: flipped ? 180 : 0 }} transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }} className="relative h-full w-full [transform-style:preserve-3d]">
        <div className="absolute inset-0 flex flex-col justify-between rounded-[1.4rem] border border-white/80 bg-mint/95 p-5 text-left [backface-visibility:hidden]">
          <p className="text-[0.6rem] font-bold uppercase tracking-[0.18em] text-ink/50">Recall / 0{index + 1}</p>
          <p className="font-display text-lg font-semibold leading-snug text-ink">{front}</p>
          <p className="text-[0.6rem] font-semibold text-ink/50">Tap to reveal answer ↗</p>
        </div>
        <div className="absolute inset-0 flex items-center rounded-[1.4rem] bg-ink p-6 text-left text-paper [backface-visibility:hidden] [transform:rotateY(180deg)]"><p className="text-sm leading-relaxed">{back}</p></div>
      </motion.div>
    </motion.button>
  );
}

export default function RememberSection() {
  const { ref, scrollYProgress } = useSectionProgress<HTMLDivElement>();
  const spread = useTransform(scrollYProgress, [0.18, 0.68], [0, 1]);
  const deckRotate = useTransform(scrollYProgress, [0.18, 0.68], [-8, 0]);
  const deckScale = useTransform(scrollYProgress, [0.18, 0.5, 0.9], [0.78, 1, 0.9]);
  const labelOpacity = useTransform(scrollYProgress, [0.1, 0.28, 0.82, 1], [0, 1, 1, 0]);

  return (
    <section id="remember" ref={ref} className="relative min-h-[170vh]">
      <div className="sticky top-0 mx-auto flex min-h-screen w-full max-w-[94rem] flex-col justify-center overflow-hidden px-6 py-24 md:px-16 lg:pl-32">
        <motion.div style={{ opacity: labelOpacity }} className="relative z-30 max-w-xl">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-mint">Stage {stage.index} · {stage.label}</p>
          <h2 className="mt-4 font-display text-4xl font-semibold leading-[1.02] tracking-[-0.05em] text-ink sm:text-6xl">Turn concepts into recall.</h2>
          <p className="mt-6 max-w-md text-base leading-relaxed text-inkSoft">{stage.description}</p>
        </motion.div>
        <div className="relative mt-4 h-[29rem] sm:h-[36rem]">
          <motion.div style={{ rotate: deckRotate, scale: deckScale }} className="absolute inset-0 [transform-style:preserve-3d]">
            <div className="absolute left-1/2 top-1/2 h-72 w-56 -translate-x-1/2 -translate-y-1/2 rounded-[1.5rem] border border-violet/15 bg-violet/[0.04] " />
            {cards.map((card, index) => <Flashcard key={card.front} {...card} index={index} spread={spread} />)}
          </motion.div>
          <motion.div style={{ opacity: labelOpacity }} className="absolute bottom-0 left-1/2 -translate-x-1/2 rounded-full border border-white/80 bg-white/70 px-4 py-2 text-[0.58rem] font-bold uppercase tracking-widest text-inkSoft ">scroll to spread · click to flip</motion.div>
        </div>
      </div>
    </section>
  );
}
