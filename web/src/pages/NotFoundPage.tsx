import React from 'react';
import { Link } from 'react-router-dom';
import { FileQuestion, ArrowLeft } from 'lucide-react';
import { Button } from '../components/ui/Button';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-6">
      <div className="w-12 h-12 rounded-full bg-white/[0.04] border border-white/[0.08] flex items-center justify-center text-em-text-dim mb-4">
        <FileQuestion className="w-6 h-6 text-em-text-muted" />
      </div>
      <span className="text-xs font-mono uppercase text-em-status-warning mb-1">404 Error</span>
      <h2 className="text-lg font-semibold text-em-text-primary mb-2">Page Not Found</h2>
      <p className="text-xs text-em-text-muted max-w-md mb-6 leading-relaxed">
        The requested URL path does not exist in the EdgeMind workspace.
      </p>
      <Link to="/">
        <Button variant="secondary" size="md" leftIcon={<ArrowLeft className="w-4 h-4" />}>
          Back to Overview
        </Button>
      </Link>
    </div>
  );
};
