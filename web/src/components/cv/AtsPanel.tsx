import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";
import { useT } from "@/i18n";
import type { AtsReport } from "../../types";

/**
 * What a machine gets back out of the compiled PDF.
 *
 * The CV is written for a person but read first by a parser, and the two can
 * disagree. This panel shows only what a parser could not recover — there is
 * deliberately no score, because "72/100" tells you nothing you can act on
 * while "your email is not in the text layer" tells you exactly what to fix.
 */
export function AtsPanel({ report }: { report: AtsReport | null | undefined }) {
  const t = useT("cv");
  // Not checked is not the same as passed, and must never look like it.
  if (report === null || report === undefined) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-dashed border-line bg-surface/40 p-3 text-sm text-muted">
        <HelpCircle size={15} className="mt-0.5 shrink-0" />
        <span>
          {t("atsNotCheckedLead")}{" "}
          <code className="rounded bg-surface px-1 py-0.5 text-xs">pip install -e '.[cv]'</code>{" "}
          {t("atsNotCheckedRest")}
        </span>
      </div>
    );
  }

  const errors = report.findings.filter((f) => f.level === "error");
  const warnings = report.findings.filter((f) => f.level === "warning");

  return (
    <section className="space-y-2.5">
      <header className="flex items-center gap-2">
        {errors.length > 0 ? (
          <XCircle size={15} className="shrink-0 text-critical" />
        ) : (
          <CheckCircle2 size={15} className="shrink-0 text-positive" />
        )}
        <h3 className="text-sm font-semibold">
          {errors.length > 0
            ? t(errors.length === 1 ? "atsBadOne" : "atsBadMany", { n: errors.length })
            : t("atsOk")}
        </h3>
        <span
          className="ml-auto font-mono text-[11px] text-muted"
          title={t("atsEngine", { engine: report.engine })}
        >
          {t("atsChars", { n: report.chars.toLocaleString() })}
        </span>
      </header>

      {[...errors, ...warnings].map((f) => (
        <div
          key={f.code}
          className={`rounded-lg border p-3 text-sm ${
            f.level === "error"
              ? "border-critical/30 bg-critical/5"
              : "border-caution/30 bg-caution/5"
          }`}
        >
          <div className="flex items-start gap-2">
            <AlertTriangle
              size={14}
              className={`mt-0.5 shrink-0 ${
                f.level === "error" ? "text-critical" : "text-caution"
              }`}
            />
            <div className="min-w-0">
              <p>{f.message}</p>
              {f.fix && <p className="mt-1 text-xs text-muted">{f.fix}</p>}
            </div>
          </div>
        </div>
      ))}

      {(report.keywords_found.length > 0 || report.keywords_missing.length > 0) && (
        <div className="rounded-lg border border-line bg-surface/40 p-3">
          <p className="mb-2 text-xs font-medium text-muted">{t("atsKeywords")}</p>
          <div className="flex flex-wrap gap-1.5">
            {report.keywords_found.map((k) => (
              <span
                key={k}
                className="rounded border border-positive/30 bg-positive/10 px-1.5 py-0.5 text-xs text-positive"
              >
                {k}
              </span>
            ))}
            {report.keywords_missing.map((k) => (
              <span
                key={k}
                className="rounded border border-line px-1.5 py-0.5 text-xs text-muted line-through decoration-muted/50"
              >
                {k}
              </span>
            ))}
          </div>
          {report.keywords_missing.length > 0 && (
            // Deliberately not a blocker: the honest fix is to gain the skill or
            // let it go, never to paste it into the CV. That is precisely what
            // the tailor guardrail exists to prevent.
            <p className="mt-2 text-xs text-muted">{t("atsKeywordsNote")}</p>
          )}
        </div>
      )}
    </section>
  );
}
