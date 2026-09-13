import type { LucideIcon } from "lucide-react";

interface MetricCardProps {
  id: string;
  label: string;
  value: string;
  context: string;
  icon: LucideIcon;
  tone: "cyan" | "amber" | "red" | "blue";
}

export default function MetricCard({ id, label, value, context, icon: Icon, tone }: MetricCardProps) {
  return <article className={`metric-card metric-card-${tone}`} data-testid={`metric-${id}`}>
    <div className="metric-card-top"><span className="metric-label">{label}</span><Icon size={17} strokeWidth={1.6} /></div>
    <div className="metric-value" data-testid={`metric-${id}-value`}>{value}</div>
    <div className="metric-context"><span className={`status-dot status-dot-${tone === "red" ? "red" : tone === "amber" ? "amber" : "cyan"}`} />{context}</div>
  </article>;
}