import React, { useEffect, useState } from 'react';
import { Check, FileJson, FileSpreadsheet } from 'lucide-react';
import { NormalizedHistoryEntry } from '../../utils/historyHelpers';
import {
  buildReportExportCsv,
  buildReportExportJson,
  getExportFilename,
  triggerBrowserDownload,
} from '../../utils/reportExport';
import { Button } from '../ui/Button';

export interface ReportExportProps {
  entry: NormalizedHistoryEntry;
  compact?: boolean;
}

export const ReportExport: React.FC<ReportExportProps> = ({ entry, compact = false }) => {
  const [exportedFormat, setExportedFormat] = useState<'json' | 'csv' | null>(null);

  useEffect(() => {
    setExportedFormat(null);
  }, [entry.id]);

  const handleExportJson = () => {
    const content = buildReportExportJson(entry);
    const filename = getExportFilename(entry, 'json');
    triggerBrowserDownload(content, filename, 'application/json;charset=utf-8');
    setExportedFormat('json');
  };

  const handleExportCsv = () => {
    const content = buildReportExportCsv(entry);
    const filename = getExportFilename(entry, 'csv');
    triggerBrowserDownload(content, filename, 'text/csv;charset=utf-8');
    setExportedFormat('csv');
  };

  return (
    <div className="inline-flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        leftIcon={
          exportedFormat === 'json' ? (
            <Check className="w-3.5 h-3.5 text-em-status-success" />
          ) : (
            <FileJson className="w-3.5 h-3.5" />
          )
        }
        onClick={handleExportJson}
        aria-label={`Export JSON report for ${entry.title}`}
      >
        {compact ? 'JSON' : 'Export JSON'}
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        leftIcon={
          exportedFormat === 'csv' ? (
            <Check className="w-3.5 h-3.5 text-em-status-success" />
          ) : (
            <FileSpreadsheet className="w-3.5 h-3.5" />
          )
        }
        onClick={handleExportCsv}
        aria-label={`Export CSV report for ${entry.title}`}
      >
        {compact ? 'CSV' : 'Export CSV'}
      </Button>
      {exportedFormat && (
        <span className="text-[11px] font-mono text-em-status-success" role="status">
          {exportedFormat.toUpperCase()} downloaded (no source code attached)
        </span>
      )}
    </div>
  );
};
