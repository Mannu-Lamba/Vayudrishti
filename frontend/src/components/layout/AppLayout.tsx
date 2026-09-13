import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import Header from "@/components/layout/Header";
import Sidebar from "@/components/layout/Sidebar";

export default function AppLayout() {
  const [navOpen, setNavOpen] = useState(false);
  return (
    <div className="app-shell">
      <Header onMenuClick={() => setNavOpen(true)} />
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <main className="app-content"><Outlet /></main>
      <Toaster position="bottom-right" richColors />
    </div>
  );
}
