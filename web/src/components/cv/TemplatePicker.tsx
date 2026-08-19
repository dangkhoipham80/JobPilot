import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
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
  const missing = !!templates && !templates.some((t) => t.id === value);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Template</CardTitle>
      </CardHeader>
      <CardBody className="pt-3">
        {error ? (
          // The document still names a template and still builds; only the
          // choice is unavailable. Say which of the two is broken.
          <p className="text-sm text-critical">
            Could not load the template list ({error}). This CV still builds with{" "}
            <span className="font-mono">{value}</span>.
          </p>
        ) : !templates ? (
          <p className="text-sm text-ink-muted">Loading templates…</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {templates.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => onChange(t.id)}
                aria-pressed={t.id === value}
                className={cn(
                  "rounded-lg border p-3 text-left transition-colors",
                  t.id === value
                    ? "border-accent bg-accent/8"
                    : "hover:bg-surface-2",
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-ink">{t.name}</span>
                  <span className="font-mono text-[11px] text-ink-muted">{t.id}</span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-ink-muted">{t.description}</p>
              </button>
            ))}
          </div>
        )}
        {missing && (
          <p className="mt-3 text-xs text-critical">
            This version names template <span className="font-mono">{value}</span>, which this
            build does not ship. Pick one above before compiling.
          </p>
        )}
      </CardBody>
    </Card>
  );
}
