import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

export interface UserPreferences {
  windUnit: "kmh" | "knots";
  pressureUnit: "hpa" | "mbar";
  alertThreshold: "moderate" | "high" | "severe";
  refreshRate: "manual" | "15m" | "30m";
  showScanlines: boolean;
}

const defaultPreferences: UserPreferences = { windUnit: "kmh", pressureUnit: "hpa", alertThreshold: "high", refreshRate: "15m", showScanlines: true };
const STORAGE_KEY = "vayudrishti-preferences";

interface PreferencesContextValue { preferences: UserPreferences; updatePreferences: (changes: Partial<UserPreferences>) => void; resetPreferences: () => void; }
const PreferencesContext = createContext<PreferencesContextValue | undefined>(undefined);

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<UserPreferences>(() => {
    try { return { ...defaultPreferences, ...JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") } as UserPreferences; } catch { return defaultPreferences; }
  });
  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences)); }, [preferences]);
  const value = useMemo(() => ({ preferences, updatePreferences: (changes: Partial<UserPreferences>) => setPreferences((current) => ({ ...current, ...changes })), resetPreferences: () => setPreferences(defaultPreferences) }), [preferences]);
  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences() {
  const context = useContext(PreferencesContext);
  if (!context) throw new Error("usePreferences must be used within PreferencesProvider");
  return context;
}

export function formatWind(kmh: number, unit: UserPreferences["windUnit"]): string {
  return unit === "knots" ? `${Math.round(kmh / 1.852)} kt` : `${kmh} km/h`;
}

export function formatPressure(hpa: number, unit: UserPreferences["pressureUnit"]): string {
  return unit === "mbar" ? `${hpa} mbar` : `${hpa} hPa`;
}