import React from 'react';
import { Badge } from '../ui/Badge';

export interface CategoryBadgeProps {
  category: string;
}

export const CategoryBadge: React.FC<CategoryBadgeProps> = ({ category }) => {
  if (!category || !category.trim()) return null;

  return (
    <Badge variant="neutral" className="max-w-full truncate">
      {category}
    </Badge>
  );
};
