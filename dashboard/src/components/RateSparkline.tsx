export function RateSparkline({ series }: { series: number[] }) {
  if (series.length === 0) {
    return <svg width="100%" height="40" aria-label="Rate sparkline empty" />;
  }
  const w = 120;
  const h = 40;
  const max = Math.max(...series, 1);
  const min = Math.min(...series, 0);
  const range = Math.max(max - min, 1);
  const points = series
    .map((v, i) => {
      const x = (i / Math.max(series.length - 1, 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} aria-label="Rate limit sparkline">
      <polyline
        fill="none"
        stroke="var(--usdc)"
        strokeWidth="2"
        points={points}
      />
    </svg>
  );
}