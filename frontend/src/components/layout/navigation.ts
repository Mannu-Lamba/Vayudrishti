import { Activity, BarChart3, CircleHelp, KeyRound, LayoutDashboard, MonitorSmartphone, Satellite, ScrollText, Settings, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavigationItem {
  label: string;
  path: string;
  icon: LucideIcon;
}

/** Shown in the top bar on wide screens and at the top of the drawer on narrow ones. */
export const primaryNavigation: NavigationItem[] = [
  { label: "Dashboard", path: "/", icon: LayoutDashboard },
  { label: "Cyclones", path: "/cyclones", icon: Activity },
  { label: "Satellite", path: "/satellite", icon: Satellite },
  { label: "Prediction", path: "/prediction", icon: Sparkles },
  { label: "History", path: "/history", icon: BarChart3 },
];

/** Account and system pages live in the profile menu (and the drawer). */
export const secondaryNavigation: NavigationItem[] = [
  { label: "Session center", path: "/sessions", icon: MonitorSmartphone },
  { label: "Audit trail", path: "/audit", icon: ScrollText },
  { label: "Methodology", path: "/about", icon: CircleHelp },
  { label: "Settings", path: "/settings", icon: Settings },
];

export const adminNavigation: NavigationItem[] = [
  { label: "Access control", path: "/admin", icon: KeyRound },
];

export const navTestId = (path: string) => `nav-link-${path === "/" ? "dashboard" : path.slice(1).replace("/", "-")}`;

const allNavigation = [...primaryNavigation, ...secondaryNavigation, ...adminNavigation];
export const pageTitle = (pathname: string) => allNavigation.find((item) => item.path === pathname)?.label ?? "Dashboard";
