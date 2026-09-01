import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import type { CvTemplate } from "@/types";

/**
 * Which LaTeX template renders this document. The set comes from the server
 * (`GET /cv/templates`) rather than a constant here: templates are directories
 * under `jobpilot/cv/templates/`, and a hardcoded list in the UI would be a
 * second opinion about what is installed — one that goes stale silently.
 *
 * The description is shown, not hidden behind a tooltip. "Awesome-CV" vs
 * "Plain" says nothing about *when* to pick either; "an ATS parser reads it in
 * order" is the entire reason the second one exists.
 */
export function TemplatePicker({
  templates,
  error,
  value,
  onChange,
}: {
  templates: CvTemplate[] | null;
  /** Why the list is missing. Without it a failed fetch reads as "still loading". */
  error?: string | null;
  value: string;
  onChange: (id: string) => void;
}) {
  // The saved document can name a template this build no longer ships (an older
  // version restored from history). Say so instead of quietly showing nothing
  // selected — the PDF will fail to build and the reason belongs here.
  const t = useT("cv");
  const missing = !!templates && !templates.some((tpl) => tpl.id === value);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("template")}</CardTitle>
      </CardHeader>
      <CardBody className="pt-3">
        {error ? (
          // The document still names a template and still builds; only the
          // choice is unavailable. Say which of the two is broken.
          <p className="text-sm text-critical">
            {t("templatesFailed", { error })} <span className="font-mono">{value}</span>.
          </p>
        ) : !templates ? (
          <p className="text-sm text-ink-muted">{t("templatesLoading")}</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {/* `name` and `description` come from the template's own manifest on
                the server, so they are shown as the backend reports them. */}
            {templates.map((tpl) => (
              <button
                key={tpl.id}
                type="button"
                onClick={() => onChange(tpl.id)}
                aria-pressed={tpl.id === value}
                className={cn(
                  "rounded-lg border p-3 text-left transition-colors",
                  tpl.id === value
                    ? "border-accent bg-accent/8"
                    : "hover:bg-surface-2",
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-ink">{tpl.name}</span>
                  <span className="font-mono text-[11px] text-ink-muted">{tpl.id}</span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-ink-muted">{tpl.description}</p>
              </button>
            ))}
          </div>
        )}
        {missing && (
          <p className="mt-3 text-xs text-critical">
            {t("templateMissingLead")} <span className="font-mono">{value}</span>
            {t("templateMissingRest")}
          </p>
        )}
      </CardBody>
    </Card>
  );
}
