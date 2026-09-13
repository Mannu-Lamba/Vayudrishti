import { useState } from "react";
import { BarChart3, CalendarDays, ChevronLeft, ChevronRight, Database, MapPin } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ApiErrorState from "@/components/common/ApiErrorState";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import LoadingBlock from "@/components/common/LoadingBlock";
import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import { useArchiveSummary, useCycloneArchive } from "@/hooks/useCyclones";

// Chart config hoisted out of render: stable references keep Recharts from re-diffing every paint.
const CHART_MARGIN = { top: 12, right: 8, left: -18, bottom: 0 };
const AXIS_TICK = { fill: "#6f7782", fontSize: 11 };
const TOOLTIP_STYLE = { background: "#1b1f24", border: "1px solid #353b44", borderRadius: 6, color: "#e4e7eb", fontSize: 12 };
const BAR_RADIUS: [number, number, number, number] = [2, 2, 0, 0];
const PAGE_SIZE = 10;

// The archive is paged through the API (GET /api/cyclones/archive?page=…) — never loaded whole.
export default function History() {
  const [page, setPage] = useState(1);
  const summary = useArchiveSummary();
  const archive = useCycloneArchive({ page, pageSize: PAGE_SIZE });
  const records = archive.data?.items ?? [];
  const total = archive.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const first = total ? (page - 1) * PAGE_SIZE + 1 : 0;
  const last = Math.min(page * PAGE_SIZE, total);
  const range = summary.data ? `${summary.data.firstYear} — ${summary.data.lastYear}` : "—";

  return <div className="page-stack" data-testid="history-page">
    <div className="page-intro-row"><div><div className="section-kicker"><BarChart3 size={13} /> ARCHIVE / {range}</div><h2 className="page-heading">Historical analysis</h2><p className="page-subheading">A reference layer for seasonal context, landfall patterns and future model training.</p></div><div className="page-intro-actions"><DataSourceBadge source={summary.source} /><span className="mock-badge"><Database size={12} /> ARCHIVE SNAPSHOT</span></div></div>
    <div className="history-top-grid">
      <Panel eyebrow="SEASONAL ACTIVITY" title="Named systems by season" data-testid="seasonal-chart-panel">
        {summary.loading ? <div className="panel-body"><LoadingBlock label="LOADING ARCHIVE SUMMARY" /></div>
          : summary.error ? <div className="panel-body"><ApiErrorState error={summary.error} onRetry={summary.refetch} subject="the archive summary" /></div>
            : <div className="history-chart" data-testid="seasonal-activity-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={summary.data?.seasons ?? []} margin={CHART_MARGIN}><CartesianGrid stroke="#2a2f36" strokeDasharray="2 4" vertical={false} /><XAxis dataKey="season" tick={AXIS_TICK} axisLine={false} tickLine={false} /><YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} /><Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,.04)" }} /><Bar dataKey="storms" fill="#5b95cf" radius={BAR_RADIUS} /></BarChart></ResponsiveContainer></div>}
      </Panel>
      <Panel eyebrow="REFERENCE WINDOW" title="Archive coverage" data-testid="archive-coverage-panel"><div className="archive-stat"><span className="archive-stat-value">{summary.data?.indexedSystems ?? "—"}</span><span>named systems indexed</span></div><div className="archive-lines"><span><CalendarDays size={14} /> {range}</span><span><MapPin size={14} /> {summary.data?.coverage ?? "—"}</span><span><Database size={14} /> {summary.source === "live" ? "Served by the archive API" : "Curated demo archive"}</span></div></Panel>
    </div>
    <Panel eyebrow="RECENT REFERENCE EVENTS" title="Historical cyclone archive" action={<DataSourceBadge source={archive.source} variant="data" />} data-testid="historical-archive-panel">
      {archive.loading ? <div className="panel-body"><LoadingBlock label="LOADING ARCHIVE" rows={4} /></div>
        : archive.error ? <div className="panel-body"><ApiErrorState error={archive.error} onRetry={archive.refetch} subject="the archive" /></div>
          : !records.length ? <div className="panel-body"><StateNotice variant="empty" title="NO HISTORICAL RECORDS" message="No archived systems match this filter." /></div>
            : <div className="history-table-wrap"><table className="history-table"><thead><tr><th>System</th><th>Season</th><th>Area / basin</th><th>Peak wind</th><th>Landfall</th><th>Record</th></tr></thead><tbody>{records.map((record) => <tr key={record.id}><td><strong>{record.name}</strong><span>{record.category}</span></td><td>{record.year}</td><td>{record.area} · {record.basin}</td><td>{record.peakWindKmh} km/h</td><td>{record.landfall}</td><td><button type="button" className="table-action" data-testid={`history-record-${record.id}-button`}><ChevronRight size={15} /></button></td></tr>)}</tbody></table></div>}
      <div className="pager" data-testid="history-pager">
        <span>{total ? `Showing ${first}–${last} of ${total}` : "No records"}</span>
        <div className="pager-buttons">
          <button type="button" className="icon-button compact" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page <= 1} aria-label="Previous page"><ChevronLeft size={14} /></button>
          <span>Page {page} / {pages}</span>
          <button type="button" className="icon-button compact" onClick={() => setPage((value) => Math.min(pages, value + 1))} disabled={page >= pages} aria-label="Next page"><ChevronRight size={14} /></button>
        </div>
      </div>
    </Panel>
  </div>;
}
