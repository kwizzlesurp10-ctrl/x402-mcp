import { useEffect, useState } from "react";
import { LiquidCanvasEffect } from "./LiquidCanvasEffect";

export function ParallaxProtocolHero() {
  const [scrollY, setScrollY] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      setScrollY(window.scrollY || document.documentElement.scrollTop);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // Multi-layer parallax scroll depths
  const gridOffsetY = scrollY * 0.15;
  const floatingOrbY = scrollY * 0.35;
  const stepCardY = scrollY * 0.05;
  const opacityFade = Math.max(0, 1 - scrollY / 600);

  return (
    <section
      style={{
        position: "relative",
        minHeight: "420px",
        overflow: "hidden",
        borderRadius: "16px",
        background: "linear-gradient(135deg, #05070E 0%, #0D111D 100%)",
        border: "1px solid rgba(0, 240, 255, 0.15)",
        boxShadow: "0 20px 50px rgba(0, 0, 0, 0.6)",
        padding: "32px",
        margin: "0 0 16px 0",
        color: "#F3F4F6",
      }}
    >
      {/* Dynamic Fluid Liquid Canvas Canvas Layer */}
      <LiquidCanvasEffect />
      {/* Background Layer 1: Animated Grid with Parallax Offset */}
      <div
        style={{
          position: "absolute",
          inset: "-50px 0",
          backgroundImage:
            "radial-gradient(circle at 1px 1px, rgba(0, 240, 255, 0.12) 1px, transparent 0)",
          backgroundSize: "28px 28px",
          transform: `translateY(${gridOffsetY}px)`,
          pointerEvents: "none",
          zIndex: 1,
        }}
      />

      {/* Background Layer 2: Floating Neon Glow Orbs */}
      <div
        style={{
          position: "absolute",
          top: "-40px",
          right: "10%",
          width: "300px",
          height: "300px",
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(0, 240, 255, 0.25) 0%, rgba(59, 130, 246, 0) 70%)",
          filter: "blur(60px)",
          transform: `translate3d(0, ${floatingOrbY}px, 0)`,
          pointerEvents: "none",
          zIndex: 2,
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: "-60px",
          left: "5%",
          width: "250px",
          height: "250px",
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(16, 185, 129, 0.2) 0%, rgba(16, 185, 129, 0) 70%)",
          filter: "blur(50px)",
          transform: `translate3d(0, ${-floatingOrbY * 0.8}px, 0)`,
          pointerEvents: "none",
          zIndex: 2,
        }}
      />

      {/* Foreground Layer 3: Main Parallax Story Content */}
      <div
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          flexDirection: "column",
          gap: "24px",
          opacity: opacityFade < 0.1 ? 0.1 : 1,
          transition: "opacity 0.2s ease-out",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                padding: "4px 12px",
                borderRadius: "20px",
                background: "rgba(0, 240, 255, 0.1)",
                border: "1px solid rgba(0, 240, 255, 0.3)",
                fontSize: "12px",
                fontFamily: "var(--font-mono, monospace)",
                color: "#00F0FF",
                marginBottom: "12px",
              }}
            >
              <span className="dot dot-cyan" aria-hidden="true" />
              x402 Micropayment Standard • V2.0 Active
            </div>
            <h1
              style={{
                fontSize: "28px",
                fontWeight: 700,
                letterSpacing: "-0.02em",
                margin: 0,
                background: "linear-gradient(90deg, #FFFFFF 0%, #00F0FF 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              Accountless Micropayments for the Agent Economy
            </h1>
            <p style={{ margin: "8px 0 0 0", color: "#9CA3AF", fontSize: "14px", maxWidth: "680px" }}>
              HTTP status code 402 native payment standard governed by the Linux Foundation. Instant,
              settled stablecoin micropayments for AI agents and HTTP resources with zero account friction.
            </p>
          </div>

          <div
            style={{
              padding: "16px 20px",
              borderRadius: "12px",
              background: "rgba(13, 17, 29, 0.75)",
              backdropFilter: "blur(16px)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
              textAlign: "right",
            }}
          >
            <div style={{ fontSize: "11px", color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Volume (30D)
            </div>
            <div style={{ fontSize: "22px", fontWeight: 700, color: "#10B981", fontFamily: "var(--font-mono, monospace)" }}>
              $12.4M+
            </div>
            <div style={{ fontSize: "12px", color: "#6B7280", marginTop: "2px" }}>
              184.5M+ settled transactions
            </div>
          </div>
        </div>

        {/* Multi-step Visual Flow Cards with Depth Offset */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: "16px",
            marginTop: "12px",
            transform: `translateY(${stepCardY}px)`,
          }}
        >
          {[
            {
              step: "01",
              title: "HTTP Request",
              desc: "Agent requests resource URL with keyless GET/POST",
              tag: "Client Request",
              color: "#3B82F6",
            },
            {
              step: "02",
              title: "402 Challenge",
              desc: "Server returns HTTP 402 with PAYMENT-REQUIRED header",
              tag: "Standard 402",
              color: "#00F0FF",
            },
            {
              step: "03",
              title: "EIP-712 Sign",
              desc: "Agent signs payment payload via wallet / facilitator",
              tag: "Agent Spend",
              color: "#8B5CF6",
            },
            {
              step: "04",
              title: "Settlement & Data",
              desc: "Resource verifies signature & returns HTTP 200 payload",
              tag: "Instant Access",
              color: "#10B981",
            },
          ].map((item) => (
            <div
              key={item.step}
              style={{
                padding: "16px",
                borderRadius: "12px",
                background: "rgba(13, 17, 29, 0.75)",
                backdropFilter: "blur(16px)",
                border: `1px solid ${item.color}33`,
                boxShadow: `0 8px 24px ${item.color}10`,
                position: "relative",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: "2px",
                  background: `linear-gradient(90deg, ${item.color}, transparent)`,
                }}
              />
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: "11px",
                  color: "#6B7280",
                  fontFamily: "var(--font-mono, monospace)",
                }}
              >
                <span>STEP {item.step}</span>
                <span style={{ color: item.color }}>{item.tag}</span>
              </div>
              <div
                style={{
                  fontSize: "16px",
                  fontWeight: 600,
                  color: "#F3F4F6",
                  margin: "8px 0 4px 0",
                }}
              >
                {item.title}
              </div>
              <div style={{ fontSize: "12px", color: "#9CA3AF", lineHeight: 1.4 }}>
                {item.desc}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
