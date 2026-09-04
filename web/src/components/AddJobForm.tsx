import { useRef, useState } from "react";
import { Loader2, Plus, Sparkles, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, Input } from "@/components/ui";
import { useT } from "@/i18n";
import { skillLabel } from "@/lib/labels";
import { useLabels } from "@/lib/labels";
import type { JdSections, JobDetail } from "@/types";

/**
 * Add a posting by hand.
 *
 * The way in for jobs no crawler may fetch — LinkedIn most of all, whose
 * robots.txt disallows automated access to its job pages. You find the posting,
 * paste it here, and everything downstream (tailor, review, apply) treats it
 * like any other job.
 *
 * The description box comes **first** because that is the order the work
 * happens in: you paste what you copied, press "let AI fill this in", and then
 * correct the six fields above it. Typing the title and company by hand still
 * works and is still the only required part — the model is a shortcut through
 * the form, not a gate in front of it.
 *
 * What the model fills in is deliberately left *editable and unmarked*. An
 * earlier shape highlighted the AI-filled fields, which read as "these are
 * done" and is the opposite of true: a blank salary means the posting never
 * printed one, and a filled one is worth a glance before it becomes a row.
 */
export function AddJobForm({ onCreated }: { onCreated: (job: JobDetail) => void }) {
  const t = useT("jobs");
  const common = useT("common");
  const labels = useLabels();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filled, setFilled] = useState(false);
  const [flags, setFlags] = useState<string[]>([]);
  const [notes, setNotes] = useState<string[]>([]);
  const [applyEmail, setApplyEmail] = useState("");
  // Not an input, because there is no skills field on this form — but it must
  // still reach `createJob`. Skills are what `derived_facets` canonicalises into
  // `skills_canonical`, which is the whole of a job's contribution to the Market
  // page's skill facet. Reading them off the posting and then dropping them on
  // the floor would leave a hand-added job invisible there — the exact gap the
  // enrichment change was written to close.
  const [skills, setSkills] = useState<string[]>([]);
  // Same reasoning as `skills`: read off the posting, no field to edit it in,
  // and it must still reach `createJob`. Reviewed on the job page after saving,
  // where the raw posting sits beside it for comparison.
  const [sections, setSections] = useState<JdSections | null>(null);
  const [workMode, setWorkMode] = useState("");
  const running = useRef(false);
  const [form, setForm] = useState({
    url: "",
    title: "",
    company: "",
    location: "",
    salary: "",
    level: "",
    apply_target: "",
    description_md: "",
  });

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: e.target.value });

  function reset() {
    setForm({
      url: "",
      title: "",
      company: "",
      location: "",
      salary: "",
      level: "",
      apply_target: "",
      description_md: "",
    });
    setFilled(false);
    setFlags([]);
    setNotes([]);
    setSkills([]);
    setSections(null);
    setWorkMode("");
    setApplyEmail("");
    setError(null);
  }

  async function read() {
    // A ref, not the `disabled` prop: two clicks in the same tick both see the
    // pre-render state and both spend a model call. Same guard, same reason, as
    // OutcomeTracker and FitCard (web/src/CLAUDE.md).
    if (running.current) return;
    if (!form.description_md.trim()) {
      setError(t("readJdEmpty"));
      return;
    }
    running.current = true;
    setReading(true);
    setError(null);
    try {
      const got = await api.readJd(form.description_md, form.url.trim());
      setForm((prev) => ({
        ...prev,
        // Only fill what the user hasn't already typed. Someone who wrote the
        // company name themselves is more reliable than a model reading around
        // a cookie banner, and having their own text replaced under them is the
        // kind of surprise that makes a helper untrustworthy.
        title: prev.title.trim() || got.title,
        company: prev.company.trim() || got.company,
        location: prev.location.trim() || got.location,
        salary: prev.salary.trim() || got.salary,
        level: prev.level.trim() || got.level,
        // The description *is* replaced: what comes back is the same paste with
        // HTML converted and blank runs collapsed, and it is what will be
        // stored, so the box should show it.
        description_md: got.description_md,
      }));
      setSkills(got.skills);
      setSections(got.sections);
      setWorkMode(got.work_mode);
      setFlags(got.flags);
      setNotes(got.notes);
      // Offered, never applied: `apply_target` is where an application would be
      // sent, and a wrong address there emails a stranger your CV.
      setApplyEmail(got.apply_email);
      setFilled(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("readJdFailed"));
    } finally {
      running.current = false;
      setReading(false);
    }
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const job = await api.createJob({
        url: form.url.trim(),
        title: form.title.trim(),
        company: form.company.trim(),
        location: form.location.trim() || null,
        salary: form.salary.trim() || null,
        level: form.level.trim() || null,
        apply_target: form.apply_target.trim() || null,
        skills,
        work_mode: workMode,
        sections,
        description_md: form.description_md,
      });
      onCreated(job);
      reset();
      setOpen(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("addJobFailed"));
    } finally {
      setBusy(false);
    }
  }

  // "Nhiệm vụ 4 · Yêu cầu 6 · Quyền lợi 3" — counts, not content. The point is
  // to show that something was captured and roughly how much, in one line; the
  // content itself belongs on the job page where the posting is beside it.
  const sectionSummary = sections
    ? (
        [
          ["secResponsibilities", sections.responsibilities.length],
          ["secMustHave", sections.must_have.length],
          ["secNiceToHave", sections.nice_to_have.length],
          ["secSoftSkills", sections.soft_skills.length],
          ["secOutputs", sections.outputs.length],
          ["secBenefits", sections.benefits.length],
        ] as const
      )
        .filter(([, n]) => n > 0)
        .map(([key, n]) => `${t(key)} ${n}`)
        .join(" · ")
    : "";

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Plus size={15} /> {t("addJob")}
      </Button>
    );
  }

  return (
    <Card className="w-full">
      <CardBody className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-sm font-semibold">{t("addJobTitle")}</h2>
            <p className="text-xs leading-relaxed text-ink-muted">{t("addJobIntro")}</p>
          </div>
          <button
            onClick={() => {
              reset();
              setOpen(false);
            }}
            aria-label={common("close")}
            className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-ink-muted hover:bg-surface-2 hover:text-ink"
          >
            <X size={15} />
          </button>
        </div>

        {/* A sample URL, not copy — it reads the same in either language. */}
        <Input
          placeholder="https://www.linkedin.com/jobs/view/…"
          value={form.url}
          onChange={set("url")}
        />

        <textarea
          rows={8}
          value={form.description_md}
          onChange={set("description_md")}
          placeholder={t("addJobJdPlaceholder")}
          className="w-full resize-y rounded-lg border bg-surface px-3 py-2 text-sm leading-relaxed text-ink placeholder:text-ink-muted/70 focus:border-accent focus:outline-none"
        />

        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Button variant="outline" size="sm" onClick={read} disabled={reading || busy}>
            {reading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Sparkles size={14} />
            )}{" "}
            {reading ? t("readJdBusy") : t("readJd")}
          </Button>
          <span className="flex-1 text-xs leading-relaxed text-ink-muted">
            {filled ? t("readJdFilled") : t("readJdHint")}
            {/* What was read but has no field on this form. Said out loud
                rather than attached quietly: it is going to be saved, and a
                user who cannot see it cannot correct it. The full text is
                reviewable on the job page, next to the original posting. */}
            {filled && sectionSummary && (
              <>
                {" "}
                <span className="text-ink">{t("readJdFound", { summary: sectionSummary })}</span>
              </>
            )}
          </span>
        </div>

        {(flags.length > 0 || skills.length > 0) && (
          <div className="flex flex-wrap items-center gap-1.5">
            {/* The crawler's own flags, in the crawler's own words — `thin_jd`
                here means exactly what it means on a crawled job's row. The
                note is the actionable line for that flag, and it is the tooltip
                rather than a paragraph because it is advice, not a finding. */}
            {flags.map((flag, i) => (
              <span
                key={flag}
                title={notes[i]}
                className="rounded-md bg-surface-2 px-2 py-0.5 text-[11px] text-ink-muted"
              >
                {labels.qualityLabel(flag)}
              </span>
            ))}
            {/* Shown because they *are* saved and there is no field to edit them
                in. A chip the user can see and delete beats a hidden list that
                silently decides which Market-page bars this job appears in. */}
            {skills.map((skill) => (
              <button
                key={skill}
                onClick={() => setSkills(skills.filter((s) => s !== skill))}
                title={common("remove")}
                className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] text-ink-muted hover:border-critical/40 hover:text-ink"
              >
                {skillLabel(skill)} <X size={10} />
              </button>
            ))}
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <Input placeholder={t("fieldTitle")} value={form.title} onChange={set("title")} />
          <Input placeholder={t("fieldCompany")} value={form.company} onChange={set("company")} />
          <Input placeholder={t("fieldLocation")} value={form.location} onChange={set("location")} />
          <Input placeholder={t("fieldSalary")} value={form.salary} onChange={set("salary")} />
        </div>

        {applyEmail && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs text-ink-muted">
            <span className="flex-1">{t("readJdApplyEmail", { email: applyEmail })}</span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setForm((prev) => ({ ...prev, apply_target: applyEmail }));
                setApplyEmail("");
              }}
            >
              {t("readJdUseEmail")}
            </Button>
          </div>
        )}

        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-ink-muted">
            {error ? <span className="text-critical">{error}</span> : t("addJobChannel")}
          </span>
          <Button onClick={submit} disabled={busy || !form.title.trim() || !form.company.trim()}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}{" "}
            {t("addJob")}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
