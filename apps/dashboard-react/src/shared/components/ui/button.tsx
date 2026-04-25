import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '../../lib/utils';

const buttonVariants = cva(
  'inline-flex min-h-9 items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-semibold transition-[background,border-color,color,transform,box-shadow] duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'border border-white/12 bg-white/10 px-4 text-slate-50 hover:-translate-y-0.5 hover:bg-white/15',
        secondary: 'border border-white/12 bg-white/5 px-4 text-slate-200 hover:-translate-y-0.5 hover:border-teal-300/40 hover:bg-teal-300/10',
        action: 'border border-radar-500 bg-radar-500 px-4 text-ink-950 shadow-[0_10px_34px_rgba(24,242,168,0.24)] hover:-translate-y-0.5 hover:bg-radar-400',
        ghost: 'border border-transparent bg-transparent px-3 text-slate-300 hover:bg-white/10 hover:text-slate-50',
        danger: 'border border-rose-200 bg-rose-50 px-4 text-rose-700 hover:-translate-y-0.5 hover:bg-rose-100',
      },
      size: {
        sm: 'min-h-8 px-3 text-xs',
        md: 'min-h-9 px-4',
        lg: 'min-h-11 px-5 text-base',
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
