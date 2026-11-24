import React from 'react';
import { cn } from '../../utils/cn';

export interface DividerProps extends React.HTMLAttributes<HTMLHRElement> {
  orientation?: 'horizontal' | 'vertical';
  className?: string;
}

export const Divider: React.FC<DividerProps> = ({
  orientation = 'horizontal',
  className,
  ...props
}) => {
  return (
    <hr
      className={cn(
        'border-0 bg-em-border-default shrink-0',
        orientation === 'horizontal' ? 'h-px w-full my-2' : 'w-px h-full mx-2 self-stretch',
        className
      )}
      {...props}
    />
  );
};
