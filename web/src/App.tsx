import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { AppRoutes } from './routes/AppRoutes';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AppShell>
        <AppRoutes />
      </AppShell>
    </BrowserRouter>
  );
};
