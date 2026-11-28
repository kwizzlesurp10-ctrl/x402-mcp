import React, { useEffect, useRef } from "react";

export interface BubbleProps {
  size?: number;
  trail?: number;
  follow?: number;
  blend?: number;
  speed?: number;
  refraction?: number;
  dispersion?: number;
  frost?: number;
  shine?: number;
  rim?: number;
  iridescence?: number;
  intensity?: number;
  ambient?: boolean;
  colorA?: [number, number, number];
  colorB?: [number, number, number];
  children?: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
}

const DEFAULT_COLOR_A: [number, number, number] = [0.2902, 0.4549, 0.7216];
const DEFAULT_COLOR_B: [number, number, number] = [0.4118, 0.4118, 0.4157];

export function Bubble({
  size = 8,
  trail = 2,
  follow = 0.35,
  blend = 2,
  speed = 1.5,
  refraction = 40,
  dispersion = 1,
  frost = 0,
  shine = 0.05,
  rim = 0.1,
  iridescence = 0.3,
  intensity = 0.15,
  ambient = false,
  colorA = DEFAULT_COLOR_A,
  colorB = DEFAULT_COLOR_B,
  children,
  style,
  className,
}: BubbleProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const colorAStr = colorA.join(",");
  const colorBStr = colorB.join(",");

  useEffect(() => {
    // Accessibility: disable canvas animation if reduced motion preferred, trail is 0, or ambient mode active
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReducedMotion || trail <= 0 || ambient) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number | null = null;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", handleResize);

    let targetX = width / 2;
    let targetY = height / 2;
    let lastMoveTime = Date.now();
    let currentAlpha = 0;
    let isMouseInWindow = false;

    // Fix min-trail clamping bug: allow 1-20 trails
    const maxTrail = Math.max(1, Math.min(20, trail));
    const points: Array<{ x: number; y: number; r: number }> = [];

    for (let i = 0; i < maxTrail; i++) {
      points.push({
        x: targetX,
        y: targetY,
        r: size * Math.max(0.4, 1 - i / (maxTrail * 2)),
      });
    }

    const startAnimation = () => {
      if (animId === null) {
        animId = requestAnimationFrame(render);
      }
    };

    const handleMouseMove = (e: MouseEvent) => {
      targetX = e.clientX;
      targetY = e.clientY;
      lastMoveTime = Date.now();
      isMouseInWindow = true;
      startAnimation();
    };

    const handleMouseLeave = () => {
      isMouseInWindow = false;
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    document.addEventListener("mouseleave", handleMouseLeave);

    let time = 0;
    const render = () => {
      const now = Date.now();
      const idleTime = now - lastMoveTime;

      // Smooth fade out when stationary (>350ms idle) or mouse left window
      if (!isMouseInWindow || idleTime > 350) {
        currentAlpha = Math.max(0, currentAlpha - 0.04);
      } else {
        currentAlpha = Math.min(1, currentAlpha + 0.08);
      }

      ctx.clearRect(0, 0, width, height);

      if (currentAlpha > 0.005) {
        time += 0.02 * speed;
        let leadX = targetX;
        let leadY = targetY;

        points.forEach((p, index) => {
          const factor = follow * (index === 0 ? 0.45 : 0.28);
          p.x += (leadX - p.x) * factor;
          p.y += (leadY - p.y) * factor;
          leadX = p.x;
          leadY = p.y;

          ctx.save();
          ctx.beginPath();
          const currentRadius = Math.max(2, p.r);
          ctx.arc(p.x, p.y, currentRadius, 0, Math.PI * 2);

          const grad = ctx.createRadialGradient(
            p.x - currentRadius * 0.35,
            p.y - currentRadius * 0.35,
            currentRadius * 0.05,
            p.x,
            p.y,
            currentRadius
          );

          const [rA, gA, bA] = colorA.map((v) => Math.floor(v * 255));
          const [rB, gB, bB] = colorB.map((v) => Math.floor(v * 255));

          const iriShift = Math.sin(time + index * 0.3) * 30 * iridescence;
          const effectiveIntensity = intensity * currentAlpha * (1 - (index / maxTrail) * 0.5);

          const hlColor = `rgba(${Math.min(255, 255 + iriShift)}, 255, 255, ${effectiveIntensity})`;
          const bodyColorA = `rgba(${rA}, ${gA}, ${bA}, ${0.35 * effectiveIntensity})`;
          const bodyColorB = `rgba(${rB}, ${gB}, ${bB}, ${0.15 * effectiveIntensity})`;

          grad.addColorStop(0, hlColor);
          grad.addColorStop(0.35, bodyColorA);
          grad.addColorStop(0.85, bodyColorB);
          grad.addColorStop(1, `rgba(0, 240, 255, ${0.2 * rim * currentAlpha})`);

          ctx.fillStyle = grad;
          if (shine > 0 && blend > 0) {
            ctx.shadowColor = `rgba(0, 240, 255, ${0.3 * shine * currentAlpha})`;
            ctx.shadowBlur = blend + refraction / 20;
          }
          ctx.fill();

          if (rim > 0) {
            ctx.strokeStyle = `rgba(255, 255, 255, ${0.3 * rim * currentAlpha})`;
            ctx.lineWidth = 0.8;
            ctx.stroke();
          }

          ctx.restore();
        });

        animId = requestAnimationFrame(render);
      } else {
        // Stop RAF loop when idle and alpha is 0 (0% CPU/GPU overhead when stationary)
        animId = null;
      }
    };

    return () => {
      if (animId !== null) cancelAnimationFrame(animId);
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, [
    size,
    trail,
    follow,
    blend,
    speed,
    refraction,
    dispersion,
    frost,
    shine,
    rim,
    iridescence,
    intensity,
    ambient,
    colorAStr,
    colorBStr,
  ]);

  return (
    <div ref={containerRef} className={className} style={{ position: "relative", width: "100%", height: "100%", ...style }}>
      <canvas
        ref={canvasRef}
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          zIndex: 15,
        }}
      />
      {children}
    </div>
  );
}
