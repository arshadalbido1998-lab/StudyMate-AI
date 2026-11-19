import { useLayoutEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

let registered = false;

function registerScrollTrigger() {
  if (!registered) {
    gsap.registerPlugin(ScrollTrigger);
    registered = true;
  }
}

export function useGsapScrollStory(
  scope: React.RefObject<HTMLElement>,
  build: (context: gsap.Context) => void
) {
  useLayoutEffect(() => {
    if (!scope.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    registerScrollTrigger();
    const context = gsap.context((self) => build(self), scope);

    return () => context.revert();
  }, [build, scope]);
}
