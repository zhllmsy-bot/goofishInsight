import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '../../lib/utils';

const buttonVariants = cva(
  'inline-flex min-h-10 items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-md)] border px-4 text-[length:var(--text-body-size)] font-semibold leading-[var(--text-body-line)] shadow-[var(--shadow-sm)] transition-[background,border-color,color,box-shadow] duration-[var(--motion-fast)] ease-[var(--ease-standard)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-600)] disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'border-[var(--brand-600)] bg-[var(--brand-600)] text-[var(--ink-inverse)] hover:border-[var(--brand-500)] hover:bg-[var(--brand-500)]',
        secondary: 'border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--ink-primary)] hover:bg-[var(--surface-2)]',
        action: 'border-[var(--brand-600)] bg-[var(--brand-600)] text-[var(--ink-inverse)] hover:border-[var(--brand-500)] hover:bg-[var(--brand-500)]',
        ghost: 'border-transparent bg-transparent px-3 text-[var(--ink-secondary)] shadow-none hover:bg-[var(--surface-2)] hover:text-[var(--ink-primary)]',
        danger: 'border-[var(--signal-danger)] bg-[var(--signal-danger)] text-[var(--ink-inverse)]',
      },
      size: {
        sm: 'min-h-8 px-3 text-[length:var(--text-caption-size)] leading-[var(--text-caption-line)]',
        md: 'min-h-10 px-4',
        lg: 'min-h-14 px-5 text-[length:var(--text-h3-size)] leading-[var(--text-h3-line)]',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  },
);

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  };

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ asChild = false, className, size, variant, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp className={cn(buttonVariants({ size, variant }), className)} ref={ref} {...props} />;
  },
);

Button.displayName = 'Button';
