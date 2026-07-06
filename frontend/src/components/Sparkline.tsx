interface Props {
  values: number[];
  width?: number;
  height?: number;
}

/** 12-point-style trend sparkline for a stat tile. Colored by whether the
 * series ends up (good) or down (critical) from its start — never a neutral
 * hue standing in for a direction judgement. */
export function Sparkline({ values, width = 96, height = 28 }: Props) {
  if (values.length < 2) {
    return <svg width={width} height={height} aria-hidden />;
  }
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const range = max - min || 1;
  const stepX = width / (values.length - 1);
  const toY = (v: number) => height - ((v - min) / range) * height;
  const points = values.map((v, i) => [i * stepX, toY(v)] as const);
  const path = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const up = values[values.length - 1] >= values[0];
  const color = up ? "var(--good)" : "var(--critical)";
  const [lastX, lastY] = points[points.length - 1];

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r={4} fill={color} stroke="var(--surface-1)" strokeWidth={2} />
    </svg>
  );
}
