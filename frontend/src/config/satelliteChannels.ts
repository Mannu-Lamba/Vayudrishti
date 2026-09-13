import type { SatelliteChannelSpec } from "@/types/satellite";

// Channel taxonomy is UI configuration (labels + operator-facing descriptions), not dataset
// content, so it lives here rather than behind the API. Per-source band details come from the
// sources endpoint.
export const SATELLITE_CHANNELS: SatelliteChannelSpec[] = [
  { id: "visible", label: "Visible", shortLabel: "VIS", requiresDaylight: true, description: "Reflected sunlight — cloud texture, overshooting tops and low-level circulation centres. Daylight only." },
  { id: "infrared", label: "Infrared", shortLabel: "IR", requiresDaylight: false, description: "Thermal emission — cloud-top temperature, convective intensity and eye structure, day and night. Primary input for Dvorak-style intensity estimation." },
  { id: "water_vapor", label: "Water Vapor", shortLabel: "WV", requiresDaylight: false, description: "Upper/mid-troposphere moisture — dry-air intrusion, outflow channels and the steering environment around the system." },
];
