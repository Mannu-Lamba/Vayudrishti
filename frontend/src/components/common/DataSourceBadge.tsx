import { FlaskConical, History, Radio } from "lucide-react";
import type { DataSource } from "@/types/api";

type BadgeVariant = "data" | "model";

const COPY: Record<DataSource, Record<BadgeVariant, string>> = {
  demo: { data: "DEMO DATA", model: "DEMO / MOCK MODEL OUTPUT" },
  live: { data: "LIVE API", model: "LIVE MODEL OUTPUT" },
  historical: { data: "HISTORICAL DATA", model: "HISTORICAL MODEL RUN" },
};

const ICON = { demo: FlaskConical, live: Radio, historical: History };

/** Provenance tag for every data/AI visualization, so demo values are never mistaken for real output. */
export default function DataSourceBadge({ source, variant = "data" }: { source?: DataSource; variant?: BadgeVariant }) {
  if (!source) return null;
  const Icon = ICON[source];
  return <span className={`source-badge source-badge-${source}`} title={`Data source: ${COPY[source].data}`} data-testid={`data-source-${source}`}><Icon size={11} />{COPY[source][variant]}</span>;
}
