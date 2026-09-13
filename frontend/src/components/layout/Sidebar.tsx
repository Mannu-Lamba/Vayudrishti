import { X } from "lucide-react";
import { NavLink } from "react-router-dom";
import BrandMark from "@/components/layout/BrandMark";
import { adminNavigation, primaryNavigation, secondaryNavigation, type NavigationItem } from "@/components/layout/navigation";
import { useAuth } from "@/lib/auth";
import { useDataMode } from "@/hooks/useDataMode";

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

function DrawerLink({ item, onClose }: { item: NavigationItem; onClose: () => void }) {
  const Icon = item.icon;
  return (
    <NavLink to={item.path} end={item.path === "/"} onClick={onClose} className={({ isActive }) => `nav-drawer-link ${isActive ? "nav-drawer-link-active" : ""}`}>
      <Icon size={17} strokeWidth={1.7} />
      <span>{item.label}</span>
    </NavLink>
  );
}

/** Navigation drawer for narrow screens; wide screens use the links in the top bar. */
export default function Sidebar({ open, onClose }: SidebarProps) {
  const { isAdmin } = useAuth();
  const { isDemo } = useDataMode();
  return (
    <>
      {open && <button type="button" aria-label="Close navigation" className="nav-drawer-scrim" onClick={onClose} data-testid="sidebar-close-scrim" />}
      <aside className={`nav-drawer ${open ? "nav-drawer-open" : ""}`} inert={!open} data-testid="app-sidebar">
        <div className="nav-drawer-head">
          <BrandMark />
          <span>VayuDrishti</span>
          <button type="button" onClick={onClose} className="icon-button" aria-label="Close navigation" data-testid="sidebar-close-button"><X size={17} /></button>
        </div>

        <div className="nav-drawer-group">Operations</div>
        <nav aria-label="Operations">
          {primaryNavigation.map((item) => <DrawerLink key={item.path} item={item} onClose={onClose} />)}
        </nav>

        <div className="nav-drawer-group">Account and system</div>
        <nav aria-label="Account and system">
          {secondaryNavigation.map((item) => <DrawerLink key={item.path} item={item} onClose={onClose} />)}
        </nav>

        {isAdmin && <>
          <div className="nav-drawer-group">Administration</div>
          <nav aria-label="Administration" data-testid="admin-navigation">
            {adminNavigation.map((item) => <DrawerLink key={item.path} item={item} onClose={onClose} />)}
          </nav>
        </>}

        <p className="nav-drawer-foot" data-testid="sidebar-data-mode">{isDemo ? "Demo data — live telemetry not connected" : "Live API mode"}</p>
      </aside>
    </>
  );
}
