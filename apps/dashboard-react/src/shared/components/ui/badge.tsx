import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '../../lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-[var(--radius-sm)] border px-2 py-1 text-[length:var(--text-caption-size)] font-semibold leading-[var(--text-caption-line)]',
  {
    variants: {
      variant: {
        default: 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--ink-secondary)]',
        action: 'border-[var(--brand-600)] bg-[var(--brand-tint)] text-[var(--brand-on-tint)]',
        success: 'border-[var(--signal-success)] bg-[var(--surface-1)] text-[var(--signal-success)]',
        danger: 'border-[var(--signal-danger)] bg-[var(--surface-1)] text-[var(--signal-danger)]',
        dark: 'border-[var(--border-subtle)] bg-[var(--surface-2)] text-[var(--ink-primary)]',
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
