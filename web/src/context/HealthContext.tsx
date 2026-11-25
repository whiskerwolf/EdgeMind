import React, { createContext, useContext } from 'react';
import { useHealth, UseHealthOptions } from '../hooks/useHealth';
import { HealthState } from '../types/api';

export interface HealthContextValue extends HealthState {
  checkHealth: () => Promise<void>;
}

const HealthContext = createContext<HealthContextValue | undefined>(undefined);

export interface HealthProviderProps extends UseHealthOptions {
  children: React.ReactNode;
}

export const HealthProvider: React.FC<HealthProviderProps> = ({
  children,
  pollingIntervalMs = 8000,
  enabled = true,
}) => {
  const health = useHealth({ pollingIntervalMs, enabled });

  return <HealthContext.Provider value={health}>{children}</HealthContext.Provider>;
};

export function useHealthContext(): HealthContextValue {
  const context = useContext(HealthContext);
  if (!context) {
    throw new Error('useHealthContext must be used within a HealthProvider');
  }
  return context;
}
