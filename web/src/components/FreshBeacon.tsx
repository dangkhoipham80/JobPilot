import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

// The signature "fresh <48h" marker — a pulsing runway beacon. Pairs a label so
// it never relies on the animation/color alone.
//
// The Vietnamese label is "mới", not "fresh": in this same UI "fresher" is a
// seniority level, and a badge reading `fresh` next to a Fresher filter would
// have two different meanings a word apart.
export function FreshBeacon({ withLabel = false, className }: { withLabel?: boolean; className?: string }) {
  const t = useT("jobs");
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)} title={t("freshTitle")}>
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-beacon rounded-full bg-accent" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
      </span>
      {withLabel && (
        <span className="font-mono text-[10px] font-medium uppercase tracking-wider text-accent">
          {t("freshBadge")}
        </span>
      )}
    </span>
  );
}
