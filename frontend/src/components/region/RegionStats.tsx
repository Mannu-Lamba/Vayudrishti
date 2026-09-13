export interface RegionStat {
  label: string;
  value: string;
  detail?: string;
  tone?: "cyan" | "amber";
}

export default function RegionStats({ stats }: { stats: RegionStat[] }) {
  return (
    <div className="region-stats" data-testid="region-stats">
      {stats.map((stat) => (
        <div className="region-stat" key={stat.label}>
          <span className="metric-label">{stat.label}</span>
          <strong className={stat.tone ? `region-stat-${stat.tone}` : ""}>{stat.value}</strong>
          {stat.detail && <small>{stat.detail}</small>}
        </div>
      ))}
    </div>
  );
}
