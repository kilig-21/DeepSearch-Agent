"use client";

import { useEffect, useRef, type HTMLAttributes, type ReactNode } from "react";

interface FadeContentProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  delay?: number;
  distance?: number;
  duration?: number;
}

/**
 * A deliberately small adaptation of React Bits' Fade Content pattern.
 * It uses the browser animation API so a single entrance effect does not
 * require shipping GSAP with the research workbench.
 */
export function FadeContent({
  children,
  className,
  delay = 0,
  distance = 8,
  duration = 360,
  ...props
}: FadeContentProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element?.animate || !window.matchMedia || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const animation = element.animate(
      [
        { opacity: 0, transform: `translateY(${distance}px)` },
        { opacity: 1, transform: "translateY(0)" },
      ],
      {
        delay,
        duration,
        easing: "cubic-bezier(0.22, 1, 0.36, 1)",
        fill: "both",
      },
    );

    return () => animation.cancel();
  }, [delay, distance, duration]);

  return (
    <div ref={ref} className={className} {...props}>
      {children}
    </div>
  );
}
