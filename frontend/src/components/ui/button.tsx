import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef } from "react";
import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:pointer-events-none disabled:opacity-45 active:scale-[0.98]",
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-white shadow-sm shadow-primary/20 hover:bg-primary-hover hover:shadow-md hover:shadow-primary/25",
        secondary:
          "bg-surface-card text-ink shadow-card border border-line/80 hover:shadow-card-hover hover:border-line",
        ghost: "text-ink-muted hover:bg-primary/5 hover:text-ink",
        destructive: "bg-status-absent-soft text-status-absent hover:bg-red-100",
        outline: "border border-line bg-transparent text-ink hover:bg-surface/80",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-lg px-3 text-xs",
        lg: "h-11 rounded-xl px-6",
        icon: "h-10 w-10 rounded-xl p-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    const resolvedVariant = variant ?? "primary";
    return (
      <Comp
        data-ui-button="true"
        data-button-variant={resolvedVariant}
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { buttonVariants };
