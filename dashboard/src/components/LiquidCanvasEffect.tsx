import { useEffect, useRef } from "react";

/**
 * LiquidCanvasEffect
 * High-performance fluid liquid canvas animation component featuring
 * organic wave physics, cyan/electric-blue/green gradients, and mouse interaction.
 */
export function LiquidCanvasEffect() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = canvas.parentElement?.clientWidth || 800);
    let height = (canvas.height = canvas.parentElement?.clientHeight || 420);

    const handleResize = () => {
      if (!canvas || !canvas.parentElement) return;
      width = canvas.width = canvas.parentElement.clientWidth;
      height = canvas.height = canvas.parentElement.clientHeight;
    };
    window.addEventListener("resize", handleResize);

    let mouseX = width / 2;
    let mouseY = height / 2;
    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      mouseX = e.clientX - rect.left;
      mouseY = e.clientY - rect.top;
    };
    canvas.addEventListener("mousemove", handleMouseMove);

    let step = 0;
    const render = () => {
      step += 0.015;
      ctx.clearRect(0, 0, width, height);

      // Primary Focused Mouse Liquid Glow Spotlight
      const mouseGrad = ctx.createRadialGradient(
        mouseX,
        mouseY,
        5,
        mouseX,
        mouseY,
        320
      );
      mouseGrad.addColorStop(0, "rgba(0, 240, 255, 0.55)");
      mouseGrad.addColorStop(0.25, "rgba(59, 130, 246, 0.35)");
      mouseGrad.addColorStop(0.65, "rgba(16, 185, 129, 0.18)");
      mouseGrad.addColorStop(1, "transparent");

      ctx.fillStyle = mouseGrad;
      ctx.fillRect(0, 0, width, height);

      // Secondary Ambient Canvas Gradient
      const ambGrad = ctx.createRadialGradient(
        width / 2,
        height / 2,
        50,
        width / 2,
        height / 2,
        Math.max(width, height)
      );
      ambGrad.addColorStop(0, "rgba(0, 240, 255, 0.08)");
      ambGrad.addColorStop(0.5, "rgba(139, 92, 246, 0.05)");
      ambGrad.addColorStop(1, "transparent");

      ctx.fillStyle = ambGrad;
      ctx.fillRect(0, 0, width, height);

      // Draw liquid wave curves (Cyan Neon Ripple)
      ctx.beginPath();
      ctx.lineWidth = 2.2;
      ctx.strokeStyle = "rgba(0, 240, 255, 0.45)";

      for (let x = 0; x < width; x += 8) {
        const y =
          height / 2 +
          Math.sin(x * 0.01 + step) * 22 +
          Math.cos(x * 0.005 + step * 0.7) * 16 +
          Math.sin((x + mouseX) * 0.008) * 12;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Second liquid wave curve (Emerald Green Accent)
      ctx.beginPath();
      ctx.lineWidth = 1.8;
      ctx.strokeStyle = "rgba(16, 185, 129, 0.35)";
      for (let x = 0; x < width; x += 10) {
        const y =
          height / 2 + 28 +
          Math.cos(x * 0.012 - step * 1.2) * 20 +
          Math.sin(x * 0.006 + step) * 14;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      if (canvas) canvas.removeEventListener("mousemove", handleMouseMove);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "auto",
        zIndex: 2,
        borderRadius: "16px",
      }}
    />
  );
}
