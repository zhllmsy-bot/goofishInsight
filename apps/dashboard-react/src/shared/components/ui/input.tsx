import * as React from "react"

import { cn } from "../../lib/utils"

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex min-h-10 w-full rounded-[var(--radius-sm)] border border-input bg-transparent px-3 py-2 text-[length:var(--text-body-size)] leading-[var(--text-body-line)] shadow-[var(--shadow-sm)] transition-[border-color,box-shadow] duration-[var(--motion-fast)] file:border-0 file:bg-transparent file:text-[length:var(--text-body-size)] file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-600)] disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
