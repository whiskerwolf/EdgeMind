import React, { useEffect, useState } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { MobileDrawer } from './MobileDrawer';
import { FooterBar } from './FooterBar';
import { HealthProvider, useHealthContext } from '../../context/HealthContext';
import { AnalysisProvider } from '../../context/AnalysisContext';
import { SettingsProvider, useOptionalSettings } from '../../context/SettingsContext';

export interface AppShellProps {
  children: React.ReactNode;
}

function isTabletViewport(): boolean {
  if (typeof window === 'undefined') return false;
  return window.innerWidth >= 768 && window.innerWidth < 1024;
}

const AppShellInner: React.FC<AppShellProps> = ({ children }) => {
  const settings = useOptionalSettings();
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    if (settings.sidebarDefaultMode === 'collapsed') return true;
    if (settings.sidebarDefaultMode === 'expanded') return false;
    return isTabletViewport();
  });
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const { status, durationMs } = useHealthContext();

  // Sync sidebar state when preference changes or when resizing in auto mode
  useEffect(() => {
    if (settings.sidebarDefaultMode === 'collapsed') {
      setSidebarCollapsed(true);
      return;
    }
    if (settings.sidebarDefaultMode === 'expanded') {
      setSidebarCollapsed(false);
      return;
    }
    setSidebarCollapsed(isTabletViewport());
  }, [settings.sidebarDefaultMode]);

  useEffect(() => {
    let wasTablet = isTabletViewport();
    const handleResize = () => {
      if (settings.sidebarDefaultMode !== 'auto') return;
      const nowTablet = isTabletViewport();
      if (nowTablet !== wasTablet) {
        wasTablet = nowTablet;
        setSidebarCollapsed(nowTablet);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [settings.sidebarDefaultMode]);

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
          className="flex-1 overflow-y-auto p-3 sm:p-4 md:p-6 bg-em-canvas"
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

const ConfiguredAppShell: React.FC<AppShellProps> = ({ children }) => {
  const settings = useOptionalSettings();
  return (
    <HealthProvider pollingIntervalMs={settings.healthPollingIntervalMs}>
      <AnalysisProvider>
        <AppShellInner>{children}</AppShellInner>
      </AnalysisProvider>
    </HealthProvider>
  );
};

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  return (
    <SettingsProvider>
      <ConfiguredAppShell>{children}</ConfiguredAppShell>
    </SettingsProvider>
  );
};
