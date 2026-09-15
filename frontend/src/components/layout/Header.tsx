import { Bell, ChevronDown, LogOut, Menu, Settings2, UserCog, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import ApiStatusIndicator from "@/components/layout/ApiStatusIndicator";
import BrandMark from "@/components/layout/BrandMark";
import { adminNavigation, navTestId, pageTitle, primaryNavigation, secondaryNavigation } from "@/components/layout/navigation";
import { useAuth } from "@/lib/auth";
import { endSession } from "@/lib/session";

interface HeaderProps { onMenuClick: () => void; }

/** The real current time in UTC (refreshed every 30 s), never a fixed demo timestamp. */
function UtcClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  const day = now.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
  const time = now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
  return <span className="topbar-clock" title="Current time (UTC)" data-testid="header-system-status">{day} · {time} UTC</span>;
}

export default function Header({ onMenuClick }: HeaderProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isAdmin } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!profileOpen) return;
    const closeOutside = (event: MouseEvent) => { if (!profileRef.current?.contains(event.target as Node)) setProfileOpen(false); };
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setProfileOpen(false); };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [profileOpen]);

  const go = (path: string) => { setProfileOpen(false); navigate(path); };
  const accountLinks = isAdmin ? [...secondaryNavigation, ...adminNavigation] : secondaryNavigation;

  return (
    <header className="topbar" data-testid="top-header">
      <div className="topbar-inner">
        <button type="button" onClick={onMenuClick} className="icon-button topbar-menu" aria-label="Open navigation" data-testid="sidebar-open-button"><Menu size={18} /></button>
        <NavLink to="/" className="topbar-brand" aria-label="VayuDrishti dashboard">
          <BrandMark />
          <span className="topbar-wordmark">VayuDrishti</span>
          <span className="topbar-wordmark-hi" lang="hi">वायुदृष्टि</span>
        </NavLink>
        <span className="topbar-page" data-testid="page-title">{pageTitle(location.pathname)}</span>
        <nav className="topbar-nav" aria-label="Primary navigation">
          {primaryNavigation.map((item) => (
            <NavLink key={item.path} to={item.path} end={item.path === "/"} data-testid={navTestId(item.path)} className={({ isActive }) => `topbar-link ${isActive ? "topbar-link-active" : ""}`}>{item.label}</NavLink>
          ))}
        </nav>
        <div className="topbar-actions">
          <ApiStatusIndicator />
          <UtcClock />
          <button type="button" className="icon-button topbar-bell" aria-label="Notifications" data-testid="header-notifications-button"><Bell size={17} /></button>
          <button type="button" className="icon-button topbar-settings" aria-label="Open settings" onClick={() => navigate("/settings")} data-testid="header-settings-button"><Settings2 size={17} /></button>
          <div className="profile-control" ref={profileRef}>
            <button type="button" className="profile-button" onClick={() => setProfileOpen((value) => !value)} aria-label="Open user profile" aria-expanded={profileOpen} data-testid="header-profile-button">{user?.picture ? <img src={user.picture} alt="" /> : <UserRound size={15} />}<span>{user?.name ?? "Operator"}</span><ChevronDown size={13} /></button>
            {profileOpen && <div className="profile-popover" data-testid="profile-popover">
              <div className="profile-popover-user"><strong>{user?.name}</strong><span>{user?.email}</span><span className={`role-badge role-badge-${user?.role ?? "analyst"}`} data-testid="profile-role-badge">{user?.role === "admin" ? <UserCog size={11} /> : <UserRound size={11} />}{(user?.role ?? "analyst").toUpperCase()}</span></div>
              <div className="profile-popover-links">
                {accountLinks.map((item) => {
                  const Icon = item.icon;
                  return <button type="button" key={item.path} className="profile-popover-link" onClick={() => go(item.path)} data-testid={item.path === "/sessions" ? "profile-sessions-link" : `profile-link-${item.path.slice(1)}`}><Icon size={14} />{item.label}</button>;
                })}
              </div>
              <button type="button" onClick={() => void endSession()} data-testid="sign-out-button"><LogOut size={14} />Sign out</button>
            </div>}
          </div>
        </div>
      </div>
    </header>
  );
}
