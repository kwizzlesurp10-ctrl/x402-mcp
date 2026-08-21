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

  colorA?: [number, number, number];
  colorB?: [number, number, number];
  children?: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
}

export function Bubble({
  size = 30,
  trail = 24,
  follow = 0.5,
  blend = 14,
  speed = 2,
  refraction = 80,
  dispersion = 1,
  frost = 0,
  shine = 0.25,
  rim = 0.5,
  iridescence = 1,
  intensity = 0.9,

  colorA = [0.2902, 0.4549, 0.7216],
  colorB = [0.4118, 0.4118, 0.4157],
  children,
  style,
  className,
}: BubbleProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", handleResize);

    // Mouse tracking positions for glassy liquid droplet trail
    let targetX = width / 2;
    let targetY = height / 2;

    const points: Array<{ x: number; y: number; vx: number; vy: number; r: number }> = [];
    const maxTrail = Math.max(5, Math.min(50, trail));

    for (let i = 0; i < maxTrail; i++) {
      points.push({ x: targetX, y: targetY, vx: 0, vy: 0, r: size * (1 - i / (maxTrail * 1.5)) });
    }

    const handleMouseMove = (e: MouseEvent) => {
      targetX = e.clientX;
      targetY = e.clientY;
    };
    window.addEventListener("mousemove", handleMouseMove);

    let time = 0;
    const render = () => {
      time += 0.02 * speed;
      ctx.clearRect(0, 0, width, height);

      // Physics interpolation for trailing glassy droplets
      let leadX = targetX;
      let leadY = targetY;

      points.forEach((p, index) => {
        const factor = follow * (index === 0 ? 0.4 : 0.25);
        p.x += (leadX - p.x) * factor;
        p.y += (leadY - p.y) * factor;
        leadX = p.x;
        leadY = p.y;

        // Render glassy droplet with iridescence, shine, and rim lighting
        ctx.save();
        ctx.beginPath();
        const currentRadius = Math.max(3, p.r);
        ctx.arc(p.x, p.y, currentRadius, 0, Math.PI * 2);

        // Glassy droplet radial gradient with colorA, colorB, and iridescence
        const grad = ctx.createRadialGradient(
          p.x - currentRadius * 0.35,
          p.y - currentRadius * 0.35,
          currentRadius * 0.05,
          p.x,
          p.y,
          currentRadius
        );

        const rA = Math.floor(colorA[0] * 255);
        const gA = Math.floor(colorA[1] * 255);
        const bA = Math.floor(colorA[2] * 255);

        const rB = Math.floor(colorB[0] * 255);
        const gB = Math.floor(colorB[1] * 255);
        const bB = Math.floor(colorB[2] * 255);

        // Iridescent reflection highlight
        const iriShift = Math.sin(time + index * 0.3) * 40 * iridescence;
        const hlColor = `rgba(${Math.min(255, 255 + iriShift)}, 255, 255, ${intensity * (1 - index / maxTrail)})`;
        const bodyColorA = `rgba(${rA}, ${gA}, ${bA}, ${0.5 * intensity * (1 - index / maxTrail)})`;
        const bodyColorB = `rgba(${rB}, ${gB}, ${bB}, ${0.2 * intensity * (1 - index / maxTrail)})`;

        grad.addColorStop(0, hlColor);
        grad.addColorStop(0.3, bodyColorA);
        grad.addColorStop(0.85, bodyColorB);
        grad.addColorStop(1, `rgba(0, 240, 255, ${0.4 * rim})`);

        ctx.fillStyle = grad;
        ctx.shadowColor = `rgba(0, 240, 255, ${0.6 * shine})`;
        ctx.shadowBlur = blend + (refraction / 10);
        ctx.fill();

        // Rim highlight stroke
        if (rim > 0) {
          ctx.strokeStyle = `rgba(255, 255, 255, ${0.5 * rim * (1 - index / maxTrail)})`;
          ctx.lineWidth = 1.2;
          ctx.stroke();
        }

        ctx.restore();
      });

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", handleMouseMove);
    };
  }, [size, trail, follow, blend, speed, refraction, dispersion, frost, shine, rim, iridescence, intensity, colorA, colorB]);

  return (
    <div ref={containerRef} className={className} style={{ position: "relative", width: "100%", height: "100%", ...style }}>
      <canvas
        ref={canvasRef}
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          zIndex: 9999,
        }}
      />
      {children}
    </div>
  );
}
