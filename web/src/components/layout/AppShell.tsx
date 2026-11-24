import React, { useState } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { MobileDrawer } from './MobileDrawer';
import { FooterBar } from './FooterBar';
import { useHealth } from '../../hooks/useHealth';

export interface AppShellProps {
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Real backend health hook
  const { status, durationMs } = useHealth({ pollingIntervalMs: 8000 });

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-em-canvas font-sans text-em-text-primary">
      {/* Desktop & Tablet Sidebar */}
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((prev) => !prev)}
      />

      {/* Mobile Off-canvas Drawer */}
      <MobileDrawer
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
      />

      {/* Main Column */}
      <div className="flex flex-col flex-1 h-full min-w-0 overflow-hidden">
        {/* Top Header */}
        <Header
          onOpenMobileMenu={() => setMobileMenuOpen(true)}
          healthStatus={status}
          durationMs={durationMs}
        />

        {/* Content Viewport */}
        <main
          className="flex-1 overflow-y-auto p-4 md:p-6 bg-em-canvas"
          role="main"
          id="main-content"
        >
          <div className="max-w-7xl mx-auto w-full">{children}</div>
        </main>

        {/* Bottom Persistent Status Bar */}
        <FooterBar healthStatus={status} durationMs={durationMs} />
      </div>
    </div>
  );
};
