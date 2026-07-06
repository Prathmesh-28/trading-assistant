import type { ReactNode } from "react";
import { Sparkline } from "./Sparkline";

interface Props {
  label: string;
  value: ReactNode;
  valueColor?: string;
  trend?: number[];
}

export function StatTile({ label, value, valueColor, trend }: Props) {
  return (
    <div className="stat-tile">
      <div className="stat-label">{label}</div>
      <div className="stat-row">
        <div className="stat-value" style={valueColor ? { color: valueColor } : undefined}>
          {value}
        </div>
        {trend && trend.length >= 2 && <Sparkline values={trend} />}
      </div>
    </div>
  );
}
