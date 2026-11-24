import { LucideIcon } from 'lucide-react';

export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: LucideIcon;
  badge?: string | number;
  section?: 'analysis' | 'management' | 'system';
}

export interface Breadcrumb {
  label: string;
  path?: string;
}
