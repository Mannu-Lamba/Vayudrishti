import MetricCard from "@/components/dashboard/MetricCard";
import type { ComponentProps } from "react";

export type MetricItem = ComponentProps<typeof MetricCard>;

/** Values are computed by the page from API/demo data — nothing is hardcoded here. */
export default function MetricGrid({ items }: { items: MetricItem[] }) {
  return <div className="metric-grid" data-testid="metric-grid">
    {items.map((item) => <MetricCard key={item.id} {...item} />)}
  </div>;
}
