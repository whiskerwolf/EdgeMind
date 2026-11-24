import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { OverviewPage } from '../pages/OverviewPage';
import { WorkspacePage } from '../pages/WorkspacePage';
import { FindingsPage } from '../pages/FindingsPage';
import { TestIntelligencePage } from '../pages/TestIntelligencePage';
import { HistoryPage } from '../pages/HistoryPage';
import { SettingsPage } from '../pages/SettingsPage';
import { NotFoundPage } from '../pages/NotFoundPage';

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/workspace" element={<WorkspacePage />} />
      <Route path="/findings" element={<FindingsPage />} />
      <Route path="/test-intelligence" element={<TestIntelligencePage />} />
      <Route path="/history" element={<HistoryPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
};
