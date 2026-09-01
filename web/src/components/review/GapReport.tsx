import { AlertTriangle, Check, Minus } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import type { RequirementStatus, TailorRequirement } from "@/types";

/**
 * The honest half of the review. Missing requirements are shown first and never
 * softened — SKILL.md §0 forbids putting them on the CV, so the only useful
 * thing to do with them is tell the user plainly. The Vietnamese copy says the
 * same thing just as bluntly; a gentler translation would be a different,
 * worse product.
 *
 * `req.text` and `req.evidence` are the agent's own words about this posting
 * and this CV — rendered as-is, never routed through the dictionary.
 */

const STATUS: Record<RequirementStatus, { icon: typeof Check; className: string }> = {
  HAVE: { icon: Check, className: "text-good" },
  PARTIAL: { icon: Minus, className: "text-accent" },
  MISSING: { icon: AlertTriangle, className: "text-critical" },
};

const ORDER: RequirementStatus[] = ["MISSING", "PARTIAL", "HAVE"];

export function GapReport({ requirements }: { requirements: TailorRequirement[] }) {
  const t = useT("review");
  const sorted = [...requirements].sort(
    (a, b) =>
      ORDER.indexOf(a.status) - ORDER.indexOf(b.status) ||
      Number(b.kind === "must_have") - Number(a.kind === "must_have"),
  );
  const missing = requirements.filter((r) => r.status === "MISSING");

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("requirements")}</CardTitle>
        {missing.length > 0 ? (
          <span className="font-mono text-[11px] text-critical">
            {t(missing.length === 1 ? "gapCountOne" : "gapCountMany", { count: missing.length })}
          </span>
        ) : (
          <span className="font-mono text-[11px] text-good">{t("noGaps")}</span>
        )}
      </CardHeader>
      <CardBody className="pt-3">
        {sorted.length === 0 ? (
          <p className="text-sm text-ink-muted">{t("noRequirements")}</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {sorted.map((req, i) => {
              const meta = STATUS[req.status];
              const Icon = meta.icon;
              return (
                <li key={i} className="flex items-start gap-2 rounded-md px-1 py-1 text-sm">
                  <Icon size={14} className={cn("mt-0.5 shrink-0", meta.className)} />
                  <div className="min-w-0 flex-1">
                    <span className={cn(req.status === "MISSING" && "font-medium")}>{req.text}</span>
                    {req.kind === "must_have" && (
                      <span className="ml-1.5 rounded border border-ink-muted/30 px-1 py-px text-[10px] uppercase tracking-wide text-ink-muted">
                        {t("must")}
                      </span>
                    )}
                    <div className="text-xs text-ink-muted">
                      {t(`req_${req.status}`)}
                      {req.evidence && ` · ${req.evidence}`}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {missing.length > 0 && (
          <p className="mt-3 rounded-lg border border-critical/30 bg-critical/6 px-3 py-2 text-xs leading-relaxed text-ink-muted">
            {t("missingNote")}
          </p>
        )}
      </CardBody>
    </Card>
  );
}
