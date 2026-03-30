import { cn } from "@/lib/cn";

const hues = ["bg-primary-soft text-primary", "bg-violet-soft text-violet", "bg-accent/15 text-accent"];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function pickHue(id: number): string {
  return hues[Math.abs(id) % hues.length];
}

export function EmployeeAvatar({ name, id, size = "md" }: { name: string; id: number; size?: "sm" | "md" }) {
  const sz = size === "sm" ? "h-8 w-8 text-[10px]" : "h-10 w-10 text-xs";
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded-xl font-semibold tracking-tight",
        pickHue(id),
        sz
      )}
    >
      {initials(name)}
    </span>
  );
}
