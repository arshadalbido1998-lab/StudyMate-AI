import { useEffect, useRef, type PropsWithChildren } from "react";
import "./GlobalParticleBackground.css";

type PointerPosition = {
  x: number;
  y: number;
  lastMovedAt: number;
};

type Pulse = {
  x: number;
  y: number;
  startedAt: number;
};

type GlobalParticleBackgroundProps = PropsWithChildren<{
  enabled?: boolean;
}>;

const settings = {
  cellSize: 70,
  color: "255, 255, 255",
  radius: 140,
  falloff: "smooth",
  holdTime: 400,
  fadeDuration: 800,
  lineWidth: 1.2,
  maxOpacity: 0.65,
  fillOpacity: 0,
  gridOpacity: 0,
  cellRadius: 0,
  clickPulse: true,
  pulseSpeed: 600,
} as const;

export default function GlobalParticleBackground({
  children,
  enabled = true,
}: GlobalParticleBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!enabled) return;
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let width = 0;
    let height = 0;
    let animationFrame: number | null = null;
    let pointer: PointerPosition | null = null;
    let pulses: Pulse[] = [];

    const stopAnimation = () => {
      if (animationFrame === null) return;
      window.cancelAnimationFrame(animationFrame);
      animationFrame = null;
    };

    const hasActiveEffect = (now: number) => {
      const pointerActive =
        pointer !== null &&
        now - pointer.lastMovedAt < settings.holdTime + settings.fadeDuration;
      const pulseActive = pulses.some(
        (pulse) => now - pulse.startedAt < settings.pulseSpeed,
      );
      return pointerActive || pulseActive;
    };

    const draw = (now: number) => {
      context.clearRect(0, 0, width, height);

      const pointerElapsed = pointer ? now - pointer.lastMovedAt : Infinity;
      const pointerOpacity = pointer
        ? reducedMotion.matches
          ? 1
          : pointerElapsed <= settings.holdTime
            ? 1
            : Math.max(
              0,
              1 - (pointerElapsed - settings.holdTime) / settings.fadeDuration,
            )
        : 0;
      pulses = pulses.filter(
        (pulse) => now - pulse.startedAt < settings.pulseSpeed,
      );

      if (pointerOpacity === 0 && pulses.length === 0) return;

      context.lineWidth = settings.lineWidth;
      context.lineJoin = "round";
      context.shadowColor = `rgba(${settings.color}, 0.45)`;
      context.shadowBlur = 8;

      for (let y = 0; y < height; y += settings.cellSize) {
        for (let x = 0; x < width; x += settings.cellSize) {
          const centerX = x + settings.cellSize / 2;
          const centerY = y + settings.cellSize / 2;
          let intensity = 0;

          if (pointer && pointerOpacity > 0) {
            const distance = Math.hypot(centerX - pointer.x, centerY - pointer.y);
            if (distance < settings.radius) {
              const normalizedDistance = distance / settings.radius;
              const spatialFalloff =
                settings.falloff === "smooth"
                  ? 1 -
                  normalizedDistance *
                  normalizedDistance *
                  (3 - 2 * normalizedDistance)
                  : 1 - normalizedDistance;
              intensity = spatialFalloff * pointerOpacity;
            }
          }

          pulses.forEach((pulse) => {
            const elapsed = now - pulse.startedAt;
            const progress = elapsed / settings.pulseSpeed;
            const waveRadius = progress * Math.hypot(width, height);
            const distance = Math.hypot(centerX - pulse.x, centerY - pulse.y);
            const waveWidth = settings.cellSize * 1.35;
            const waveIntensity =
              Math.max(0, 1 - Math.abs(distance - waveRadius) / waveWidth) *
              (1 - progress);
            intensity = Math.max(intensity, waveIntensity);
          });

          if (intensity <= 0) continue;

          const opacity = Math.min(
            1,
            settings.gridOpacity + intensity * settings.maxOpacity,
          );
          if (settings.fillOpacity > 0) {
            context.fillStyle = `rgba(${settings.color}, ${intensity * settings.fillOpacity
              })`;
            context.beginPath();
            context.roundRect(
              x,
              y,
              settings.cellSize,
              settings.cellSize,
              settings.cellRadius,
            );
            context.fill();
          }

          context.strokeStyle = `rgba(${settings.color}, ${opacity})`;
          context.beginPath();
          context.roundRect(
            x,
            y,
            settings.cellSize,
            settings.cellSize,
            settings.cellRadius,
          );
          context.stroke();
        }
      }
      context.shadowBlur = 0;
    };

    const animate = (timestamp: number) => {
      animationFrame = null;
      if (document.hidden) return;

      draw(timestamp);
      if (hasActiveEffect(timestamp)) {
        animationFrame = window.requestAnimationFrame(animate);
      }
    };

    const requestDraw = () => {
      if (reducedMotion.matches) {
        stopAnimation();
        draw(performance.now());
      } else if (!document.hidden && animationFrame === null) {
        animationFrame = window.requestAnimationFrame(animate);
      }
    };

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.round(width * pixelRatio);
      canvas.height = Math.round(height * pixelRatio);
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      requestDraw();
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      pointer = {
        x: event.clientX,
        y: event.clientY,
        lastMovedAt: performance.now(),
      };
      requestDraw();
    };

    const handlePointerOut = (event: PointerEvent) => {
      if (event.relatedTarget !== null) return;
      pointer = null;
      requestDraw();
    };

    const handleClick = (event: MouseEvent) => {
      if (!settings.clickPulse || reducedMotion.matches || event.detail === 0) return;
      pulses.push({
        x: event.clientX,
        y: event.clientY,
        startedAt: performance.now(),
      });
      requestDraw();
    };

    const handleMotionPreferenceChange = () => {
      if (reducedMotion.matches) {
        stopAnimation();
        pulses = [];
        draw(performance.now());
      } else {
        requestDraw();
      }
    };

    const handleVisibilityChange = () => {
      if (document.hidden) stopAnimation();
      else requestDraw();
    };

    resize();
    window.addEventListener("resize", resize, { passive: true });
    document.addEventListener("pointermove", handlePointerMove, { passive: true });
    document.addEventListener("pointerout", handlePointerOut, { passive: true });
    document.addEventListener("click", handleClick, { passive: true });
    document.addEventListener("visibilitychange", handleVisibilityChange);
    reducedMotion.addEventListener("change", handleMotionPreferenceChange);

    return () => {
      stopAnimation();
      window.removeEventListener("resize", resize);
      document.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("pointerout", handlePointerOut);
      document.removeEventListener("click", handleClick);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      reducedMotion.removeEventListener("change", handleMotionPreferenceChange);
    };
  }, [enabled]);

  return (
    <div className={`global-particle-background${enabled ? "" : " is-disabled"}`}>
      {enabled && (
        <canvas
          ref={canvasRef}
          className="global-particle-background__canvas"
          aria-hidden="true"
        />
      )}
      <div className="global-particle-background__content">{children}</div>
    </div>
  );
}
