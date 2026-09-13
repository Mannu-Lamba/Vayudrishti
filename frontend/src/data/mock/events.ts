import type { OperationalEvent } from "@/types/cyclone";

// DEMO operational feed. Phase 6: GET /api/events.
export const mockOperationalEvents: OperationalEvent[] = [
  { id: "evt-vd001-threshold", kind: "alert", priority: "high", title: "VD-001 crossed severe storm threshold", source: "Detection pipeline", timestamp: "2026-09-08T14:18:00Z", cycloneId: "vd-001" },
  { id: "evt-insat3d-1430", kind: "satellite", priority: "info", title: "INSAT-3D infrared frame processed", source: "Satellite intelligence", timestamp: "2026-09-08T14:30:00Z" },
  { id: "evt-forecast-1435", kind: "forecast", priority: "info", title: "Demo forecast refreshed", source: "Prediction center", timestamp: "2026-09-08T14:35:00Z" },
];
