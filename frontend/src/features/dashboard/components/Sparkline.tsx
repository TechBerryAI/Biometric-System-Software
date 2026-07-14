import { toSpark } from "@/features/dashboard/utils/formatters";

export function Sparkline({ points }: { points: number[] }) {
  return (
    <div className="mt-3 h-10 rounded-xl bg-slate-50/80 px-2 py-2">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full">
        <polyline
          fill="none"
          stroke="#4F46E5"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={toSpark(points)}
        />
      </svg>
    </div>
  );
}
