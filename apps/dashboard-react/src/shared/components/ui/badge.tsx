import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '../../lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold leading-none',
  {
    variants: {
      variant: {
        default: 'border-white/12 bg-white/8 text-slate-200',
        action: 'border-radar-500 bg-radar-500 text-ink-950',
        success: 'border-radar-500/45 bg-radar-500/12 text-radar-400',
        danger: 'border-rose-200 bg-rose-50 text-rose-700',
        dark: 'border-white/12 bg-ink-950 text-slate-100',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export type BadgeProps = React.HTMLAttributes<HTMLSpanElement> &
  VariantProps<typeof badgeVariants>;

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
