interface PersistenceBannerProps {
  redisMode: string;
  hasRevenue: boolean;
}

export function PersistenceBanner({ redisMode, hasRevenue }: PersistenceBannerProps) {
  if (redisMode !== "memory") return null;

  const className = hasRevenue ? "banner banner-red" : "banner banner-amber";

  return (
    <div className={className} role="alert">
      <span className="dot dot-amber" aria-hidden="true" />
      <span>
        In-memory store — quota, tiers, and credits reset on restart.
        {hasRevenue && " Revenue detected — "}
        Set <code style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}>REDIS_URL</code>
        {hasRevenue ? " before selling to real buyers." : " for persistent storage."}
      </span>
    </div>
  );
}
