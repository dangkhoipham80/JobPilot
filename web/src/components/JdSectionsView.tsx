import { Award, CheckCircle2, Gift, ListChecks, Send, Sparkles, Target, Users } from "lucide-react";
import { useT } from "@/i18n";
import type { JdSections } from "@/types";

/**
 * A posting's body, bucketed — the same text as the raw JD, arranged.
 *
 * Deliberately a *view* rather than a card of its own: it renders inside the
 * job description card behind a toggle, because it is a reading of that text
 * and not a second source. The raw posting is always one click away, which is
 * what makes it safe to show a model's arrangement of someone's job ad at all —
 * every line here can be checked against the original in the other tab of the
 * same card.
 *
 * Empty buckets are omitted rather than shown empty. "Outputs: —" on nine jobs
 * out of ten is a row that teaches you to stop reading rows; a posting that
 * genuinely names deliverables is worth noticing precisely because most don't.
 */

const ORDER = [
  { key: "role", icon: Target, label: "secRole" },
  { key: "responsibilities", icon: ListChecks, label: "secResponsibilities" },
  { key: "must_have", icon: CheckCircle2, label: "secMustHave" },
  { key: "nice_to_have", icon: Sparkles, label: "secNiceToHave" },
  { key: "soft_skills", icon: Users, label: "secSoftSkills" },
  { key: "outputs", icon: Award, label: "secOutputs" },
  { key: "benefits", icon: Gift, label: "secBenefits" },
  { key: "how_to_apply", icon: Send, label: "secHowToApply" },
] as const satisfies readonly { key: keyof JdSections; icon: unknown; label: string }[];

export function JdSectionsView({ sections }: { sections: JdSections }) {
  const t = useT("jobs");

  const blocks = ORDER.map(({ key, icon, label }) => {
    const value = sections[key];
    const items = Array.isArray(value) ? value : value.trim() ? [value] : [];
    return items.length ? { key, icon, label, items, prose: !Array.isArray(value) } : null;
  }).filter((b): b is NonNullable<typeof b> => b !== null);

  if (!blocks.length) return null;

  return (
    <div className="space-y-5">
      {blocks.map(({ key, icon: Icon, label, items, prose }) => (
        <section key={key}>
          <h4 className="mb-2 inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            <Icon size={13} /> {t(label)}
          </h4>
          {prose ? (
            // `role` and `how_to_apply` are single statements, not lists — a
            // one-item bullet reads as a list someone forgot to finish.
            <p className="text-sm leading-relaxed text-ink">{items[0]}</p>
          ) : (
            <ul className="space-y-1.5">
              {items.map((item, i) => (
                <li key={i} className="flex gap-2 text-sm leading-relaxed text-ink">
                  <span aria-hidden className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ink-muted" />
                  {/* The posting's own words — never translated, never restyled. */}
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
