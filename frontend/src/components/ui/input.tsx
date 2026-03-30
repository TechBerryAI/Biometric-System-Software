import { forwardRef } from "react";
import { cn } from "@/lib/cn";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, InputProps>(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-xl border border-line bg-surface-card px-3.5 py-2 text-sm text-ink shadow-sm transition-shadow duration-200",
        "placeholder:text-ink-subtle",
        "hover:border-line focus-visible:border-primary/40 focus-visible:ring-2 focus-visible:ring-primary/15",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      ref={ref}
      {...props}
    />
  );
});
Input.displayName = "Input";
