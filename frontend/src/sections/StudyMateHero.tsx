import { useEffect, useLayoutEffect, useRef, useState, type AnimationEvent } from "react";
import { Link } from "react-router-dom";
import gsap from "gsap";
import "./StudyMateHero.css";

const TAU = Math.PI * 2;
const heroTitleLines = ["Turn your notes", "into understanding."];

type StudyMateHeroProps = {
  userName?: string;
};

function renderTitleCharacters(line: string, lineIndex: number) {
  return Array.from(line).map((character, characterIndex) => (
    <span
      key={`${lineIndex}-${characterIndex}`}
      className="study-hero__title-character"
      data-hero-character
      aria-hidden="true"
    >
      {character === " " ? "\u00a0" : character}
    </span>
  ));
}

export default function StudyMateHero({ userName }: StudyMateHeroProps) {
  const heroRef = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const nameTiltRef = useRef<HTMLSpanElement>(null);
  const eyeRef = useRef<HTMLDivElement>(null);
  const irisRef = useRef<HTMLDivElement>(null);
  const pupilRef = useRef<HTMLDivElement>(null);
  const orbitRef = useRef<HTMLDivElement>(null);
  const rotationActiveRef = useRef(false);
  const [rotationActive, setRotationActive] = useState(false);

  useLayoutEffect(() => {
    const title = titleRef.current;
    if (!title || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const context = gsap.context(() => {
      gsap.fromTo(
        "[data-hero-character]",
        { yPercent: 42, opacity: 0, filter: "blur(7px)", rotateX: 9 },
        {
          yPercent: 0,
          opacity: 1,
          filter: "blur(0px)",
          rotateX: 0,
          duration: 0.72,
          stagger: 0.016,
          ease: "power3.out",
          clearProps: "filter",
        }
      );
    }, title);

    return () => context.revert();
  }, []);

  useEffect(() => {
    const title = titleRef.current;
    const tiltElement = nameTiltRef.current;
    if (!userName || !title || !tiltElement) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const target = { x: 0, y: 0 };
    const current = { x: 0, y: 0 };
    let frameId = 0;

    const animateTilt = () => {
      frameId = 0;
      current.x += (target.x - current.x) * 0.16;
      current.y += (target.y - current.y) * 0.16;
      tiltElement.style.setProperty("--name-tilt-x", `${current.x}deg`);
      tiltElement.style.setProperty("--name-tilt-y", `${current.y}deg`);

      if (Math.abs(target.x - current.x) > 0.01 || Math.abs(target.y - current.y) > 0.01) {
        frameId = requestAnimationFrame(animateTilt);
      } else {
        current.x = target.x;
        current.y = target.y;
        tiltElement.style.setProperty("--name-tilt-x", `${current.x}deg`);
        tiltElement.style.setProperty("--name-tilt-y", `${current.y}deg`);
      }
    };

    const scheduleTilt = () => {
      if (!frameId) frameId = requestAnimationFrame(animateTilt);
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (event.pointerType === "touch" || reducedMotion.matches) return;
      const rect = title.getBoundingClientRect();
      const horizontal = Math.max(-1, Math.min(1, (event.clientX - (rect.left + rect.width / 2)) / (rect.width / 2)));
      const vertical = Math.max(-1, Math.min(1, (event.clientY - (rect.top + rect.height / 2)) / (rect.height / 2)));
      target.x = vertical * -6;
      target.y = horizontal * 8;
      scheduleTilt();
    };

    const handlePointerLeave = () => {
      target.x = 0;
      target.y = 0;
      scheduleTilt();
    };

    title.addEventListener("pointermove", handlePointerMove, { passive: true });
    title.addEventListener("pointerleave", handlePointerLeave, { passive: true });

    return () => {
      title.removeEventListener("pointermove", handlePointerMove);
      title.removeEventListener("pointerleave", handlePointerLeave);
      cancelAnimationFrame(frameId);
    };
  }, [userName]);

  const handleNameDoubleClick = () => {
    if (!userName || rotationActiveRef.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    rotationActiveRef.current = true;
    setRotationActive(true);
  };

  const handleRotationEnd = (event: AnimationEvent<HTMLSpanElement>) => {
    if (event.target !== event.currentTarget) return;
    rotationActiveRef.current = false;
    setRotationActive(false);
  };

  useEffect(() => {
    const hero = heroRef.current;
    const eye = eyeRef.current;
    const iris = irisRef.current;
    const pupil = pupilRef.current;
    const orbit = orbitRef.current;
    if (!hero || !eye || !iris || !pupil || !orbit) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const touchDevice = window.matchMedia("(pointer: coarse)").matches;
    const pointer = { irisX: 0, irisY: 0, pupilX: 0, pupilY: 0, active: false, lastMove: 0 };
    const current = { irisX: 0, irisY: 0, pupilX: 0, pupilY: 0 };
    const start = performance.now();
    let frameId = 0;

    const updatePointer = (event: PointerEvent) => {
      if (touchDevice) return;
      const rect = hero.getBoundingClientRect();
      const mouseX = event.clientX - rect.left;
      const mouseY = event.clientY - rect.top;
      const eyeRect = eye.getBoundingClientRect();
      const eyeCenterX = eyeRect.left + eyeRect.width / 2 - rect.left;
      const eyeCenterY = eyeRect.top + eyeRect.height / 2 - rect.top;
      const dx = mouseX - eyeCenterX;
      const dy = mouseY - eyeCenterY;
      const angle = Math.atan2(dy, dx);
      const distance = Math.sqrt(dx * dx + dy * dy);
      const irisDistance = Math.min(distance, 28);
      const pupilDistance = Math.min(distance, 42);
      pointer.irisX = Math.cos(angle) * irisDistance;
      pointer.irisY = Math.sin(angle) * irisDistance;
      pointer.pupilX = Math.cos(angle) * pupilDistance;
      pointer.pupilY = Math.sin(angle) * pupilDistance;
      pointer.active = true;
      pointer.lastMove = performance.now();
    };

    const resetPointer = () => {
      pointer.active = false;
    };

    const animate = (now: number) => {
      const elapsed = (now - start) / 1000;
      const angle = elapsed * (TAU / 12) - Math.PI / 2;
      const orbitX = Math.cos(angle);
      const orbitY = Math.sin(angle);
      const orbitRadius = Math.min(330, Math.max(175, window.innerWidth * 0.22));
      orbit.style.transform = `translate3d(${orbitX * orbitRadius}px, ${orbitY * orbitRadius}px, 0)`;

      const pointerFresh = pointer.active && now - pointer.lastMove < 900;
      const targetIrisX = pointerFresh ? pointer.irisX : orbitX * 28;
      const targetIrisY = pointerFresh ? pointer.irisY : orbitY * 28;
      const targetPupilX = pointerFresh ? pointer.pupilX : orbitX * 42;
      const targetPupilY = pointerFresh ? pointer.pupilY : orbitY * 42;
      current.irisX += (targetIrisX - current.irisX) * 0.08;
      current.irisY += (targetIrisY - current.irisY) * 0.08;
      current.pupilX += (targetPupilX - current.pupilX) * 0.08;
      current.pupilY += (targetPupilY - current.pupilY) * 0.08;

      iris.style.transform = `translate3d(calc(-50% + ${current.irisX}px), calc(-50% + ${current.irisY}px), 0)`;
      pupil.style.transform = `translate3d(calc(-50% + ${current.pupilX}px), calc(-50% + ${current.pupilY}px), 0)`;

      if (!reducedMotion) frameId = requestAnimationFrame(animate);
    };

    hero.addEventListener("pointermove", updatePointer, { passive: true });
    hero.addEventListener("pointerleave", resetPointer, { passive: true });
    animate(start);

    return () => {
      hero.removeEventListener("pointermove", updatePointer);
      hero.removeEventListener("pointerleave", resetPointer);
      cancelAnimationFrame(frameId);
    };
  }, []);

  return (
    <section ref={heroRef} id="home" className="study-hero" aria-label="StudyMate AI interactive introduction">
      <div className="study-hero__atmosphere" aria-hidden="true" />
      <div className="study-hero__content">
        <p className="study-hero__eyebrow"><span /> Study smarter, stay curious</p>
        <h2
          ref={titleRef}
          aria-label={userName || heroTitleLines.join(" ")}
          onDoubleClick={handleNameDoubleClick}
          className={`study-hero__heading${userName ? " study-hero__title--interactive" : ""}`}
        >
          {userName ? (
            <span ref={nameTiltRef} className="study-hero__name-tilt">
              <span
                className={`study-hero__name-rotation${rotationActive ? " is-rotating" : ""}`}
                onAnimationEnd={handleRotationEnd}
              >
                <span className="study-hero__title-line study-hero__title-line--accent">
                  <span className="study-hero__title-character" data-hero-character>
                    {userName}
                  </span>
                </span>
              </span>
            </span>
          ) : (
            <>
              <span className="study-hero__title-line" aria-hidden="true">{renderTitleCharacters(heroTitleLines[0], 0)}</span>
              <span className="study-hero__title-line study-hero__title-line--accent" aria-hidden="true">{renderTitleCharacters(heroTitleLines[1], 1)}</span>
            </>
          )}
        </h2>
        <p className="study-hero__copy">AI-powered tools that transform your study material into summaries, concepts, flashcards, quizzes and personalized answers.</p>
        <div className="study-hero__actions">
          <Link to="/chat#chat-workspace">Start studying <span>↗</span></Link>
          <span className="study-hero__prompt"><i /> Move your cursor</span>
        </div>
      </div>

      <div className="study-eye__scene" aria-hidden="true">
        <div className="study-eye__glass" />
        <div ref={orbitRef} className="study-eye__orbit"><span /></div>
        <div ref={eyeRef} className="study-eye">
          <div className="study-eye__lid" />
          <div ref={irisRef} className="study-eye__iris"><div ref={pupilRef} className="study-eye__pupil"><span /></div></div>
          <span className="study-eye__mark study-eye__mark--top">01 / ATTENTION</span>
          <span className="study-eye__mark study-eye__mark--bottom">LIVE LEARNING SYSTEM</span>
        </div>
      </div>

      <div className="study-hero__scroll" aria-hidden="true"><span /> Scroll to begin</div>
    </section>
  );
}