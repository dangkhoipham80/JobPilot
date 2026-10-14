import { useEffect, useRef, useState } from "react";
import { ExternalLink, ImageUp, Loader2, Plus, Sparkles, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, Input, Select } from "@/components/ui";
import { useT } from "@/i18n";
import { skillLabel, sourceLabel } from "@/lib/labels";
import { useLabels } from "@/lib/labels";
import {
  IMPORT_TYPES,
  MAX_IMPORT_FILES,
  UploadError,
  prepareImportFile,
  readAsDataUri,
} from "@/lib/upload";
import { HAND_SOURCES, type HandSource, type JdSections, type JobDetail } from "@/types";

/** The source a posting's address gives away, or null when it gives none. Only
 *  a default: the select stays the user's to change, and what they pick wins. */
export function sourceFromUrl(url: string): HandSource | null {
  let host: string;
  try {
    // An address copied without its scheme is still an address.
    const typed = url.trim();
    host = new URL(typed.includes("://") ? typed : `https://${typed}`).hostname.toLowerCase();
  } catch {
    return null;
  }
  const on = (...domains: string[]) => domains.some((d) => host === d || host.endsWith(`.${d}`));
  if (on("facebook.com", "fb.com", "fb.me")) return "facebook";
  if (on("linkedin.com", "lnkd.in")) return "linkedin";
  if (on("zalo.me")) return "zalo";
  return null;
}

/** What a file reading left on the form: which kind it was, the model's notes,
 *  and the uploaded files as object URLs so the original opens beside the box. */
interface FileNote {
  transcribed: boolean;
  unreadable: string[];
  sources: { name: string; url: string }[];
  /** The text exactly as the reading put it in the box — what tells "still the
   *  file's words" from "the file's words plus the user's corrections". */
  text: string;
}

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
 *
 * A posting that exists only as a picture — a screenshot of a Facebook post, a
 * hiring poster — comes in through the same box: the file is turned into text
 * *in the description box*, and the fields are then read from that text exactly
 * as from a paste. The box is the checkpoint. What gets stored as the job's
 * description is what was in it, with the picture one click away to hold it
 * against, and the note under it says whether a model typed those words or the
 * PDF carried them.
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
  // null = the user has not chosen. The address then decides, and failing that
  // nothing is sent at all — see `submit`.
  const [source, setSource] = useState<HandSource | null>(null);
  const [fileBusy, setFileBusy] = useState(false);
  const [fileNote, setFileNote] = useState<FileNote | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const running = useRef(false);
  // The address as it is *now*. `read` can run from a closure made before a
  // file reading began (`readFiles` awaits a model, then calls it), and the
  // address typed during that wait is the one the reader should be given.
  const urlNow = useRef("");
  const cv = useT("cv");

  // The object URLs behind "Original" live exactly as long as the reading that
  // made them: replaced by the next one, dropped on reset, on unmount. Keyed on
  // the `sources` array, not the note — the note is re-made when its text
  // snapshot is refreshed, and revoking then would kill links still on screen.
  const linked = fileNote?.sources;
  useEffect(() => {
    return () => linked?.forEach((s) => URL.revokeObjectURL(s.url));
  }, [linked]);
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
  urlNow.current = form.url;

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
    setSource(null);
    setFileNote(null);
    setError(null);
  }

  // A reading replaces the box, so it may only land where that loses nothing:
  // an empty box, or one still holding the last reading untouched.
  const boxIsFree =
    !form.description_md.trim() || (fileNote !== null && form.description_md === fileNote.text);

  async function readFiles(picked: File[]) {
    if (running.current || !picked.length) return;
    if (!boxIsFree) {
      setError(t("readFileBlocked"));
      return;
    }
    if (picked.length > MAX_IMPORT_FILES) {
      setError(cv("importTooMany", { max: MAX_IMPORT_FILES }));
      return;
    }
    running.current = true;
    setFileBusy(true);
    setError(null);
    let text = "";
    try {
      const ready: File[] = [];
      for (const file of picked) ready.push(await prepareImportFile(file));
      const payload = await Promise.all(
        ready.map(async (file) => ({ name: file.name, data: await readAsDataUri(file) })),
      );
      const got = await api.readJdFile(payload);
      text = got.text;
      setForm((prev) => ({ ...prev, description_md: got.text }));
      setFileNote({
        transcribed: got.transcribed,
        unreadable: got.unreadable,
        sources: ready.map((file) => ({ name: file.name, url: URL.createObjectURL(file) })),
        text: got.text,
      });
      // Whatever was read off an earlier text no longer describes this one.
      setFilled(false);
    } catch (e) {
      if (e instanceof UploadError) {
        const key =
          e.problem === "type"
            ? "importUnsupported"
            : e.problem === "size"
              ? "importTooLarge"
              : "importUndecodable";
        setError(cv(key, { name: e.file }));
      } else {
        setError(e instanceof ApiError ? e.message : t("readFileFailed"));
      }
    } finally {
      running.current = false;
      setFileBusy(false);
    }
    // Straight on to the fields, as if the text had been pasted and the button
    // pressed. Passed in rather than read from state: this render's `form` is
    // the one from before the text arrived.
    if (text) await read(text);
  }

  async function read(fromFile?: string) {
    // A ref, not the `disabled` prop: two clicks in the same tick both see the
    // pre-render state and both spend a model call. Same guard, same reason, as
    // OutcomeTracker and FitCard (web/src/CLAUDE.md).
    if (running.current) return;
    const body = fromFile ?? form.description_md;
    // Is the box, right now, exactly what a file reading put there? (`fileNote`
    // is a render behind when this runs straight after the reading.)
    const fileText = fromFile !== undefined || (fileNote !== null && body === fileNote.text);
    if (!body.trim()) {
      setError(t("readJdEmpty"));
      return;
    }
    running.current = true;
    setReading(true);
    setError(null);
    try {
      const got = await api.readJd(body, urlNow.current.trim());
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
      // The tidied text is still the file's own: keep the note's snapshot in
      // step, or the next upload would be refused as "you edited this".
      if (fileText) {
        setFileNote((prev) => (prev ? { ...prev, text: got.description_md } : prev));
      }
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
        // Left out when nobody said and the address does not tell: re-saving a
        // posting must not relabel a job the user already filed under Facebook.
        source: source ?? sourceFromUrl(form.url) ?? undefined,
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

        <div className="flex flex-wrap items-center gap-2">
          {/* A sample URL, not copy — it reads the same in either language. */}
          <Input
            className="min-w-[14rem] flex-1"
            placeholder="https://www.linkedin.com/jobs/view/…"
            value={form.url}
            onChange={set("url")}
          />
          <label className="flex items-center gap-2 text-xs text-ink-muted">
            {t("foundOn")}
            <Select
              value={source ?? sourceFromUrl(form.url) ?? "manual"}
              onChange={(e) => setSource(e.target.value as HandSource)}
            >
              {HAND_SOURCES.map((key) => (
                <option key={key} value={key}>
                  {key === "manual" ? t("foundElsewhere") : sourceLabel(key)}
                </option>
              ))}
            </Select>
          </label>
        </div>

        <textarea
          rows={8}
          value={form.description_md}
          onChange={set("description_md")}
          // Locked while either reading is out: both replace what is in the
          // box when they land, and a sentence typed during the wait would be
          // gone without a word. (Checked in a browser: it was.)
          readOnly={fileBusy || reading}
          onPaste={(e) => {
            // A screenshot on the clipboard is the commonest way a Facebook post
            // arrives. Only when there is no text beside it: a copy out of a
            // spreadsheet or a word processor carries the text *and* a picture
            // of it, and the text is what was meant.
            const pasted = Array.from(e.clipboardData.files);
            if (!pasted.length || e.clipboardData.getData("text/plain").trim()) return;
            e.preventDefault();
            void readFiles(pasted);
          }}
          placeholder={t("addJobJdPlaceholder")}
          className="w-full resize-y rounded-lg border bg-surface px-3 py-2 text-sm leading-relaxed text-ink placeholder:text-ink-muted/70 read-only:opacity-70 focus:border-accent focus:outline-none"
        />

        {fileNote && (
          <div className="rounded-lg border border-accent/40 bg-accent/5 px-3 py-2 text-xs leading-relaxed text-ink-muted">
            <p className="text-ink">
              {t(fileNote.transcribed ? "readFileTranscribed" : "readFileLayer")}
            </p>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              <span>{t("readFileOriginal")}</span>
              {fileNote.sources.map((s, i) => (
                <a
                  key={s.url}
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-ink underline decoration-ink-muted/50 underline-offset-2 hover:decoration-ink"
                >
                  {s.name || t("readFilePage", { n: i + 1 })} <ExternalLink size={11} />
                </a>
              ))}
            </p>
            {fileNote.unreadable.length > 0 && (
              <div className="mt-1.5">
                <p className="text-ink">{t("readFileUnreadable")}</p>
                <ul className="mt-0.5 flex flex-col gap-0.5">
                  {/* The model's own sentences, in the posting's language. */}
                  {fileNote.unreadable.map((note, i) => (
                    <li key={i} className="flex gap-1.5">
                      <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ink-muted" />
                      <span>{note}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void read()}
            disabled={reading || fileBusy || busy}
          >
            {reading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Sparkles size={14} />
            )}{" "}
            {reading ? t("readJdBusy") : t("readJd")}
          </Button>
          <input
            ref={picker}
            type="file"
            multiple
            accept={IMPORT_TYPES.join(",")}
            className="hidden"
            onChange={(e) => {
              if (e.target.files) void readFiles(Array.from(e.target.files));
              // Same file twice in a row must still fire `change`.
              e.target.value = "";
            }}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => picker.current?.click()}
            disabled={reading || fileBusy || busy || !boxIsFree}
            title={boxIsFree ? undefined : t("readFileBlocked")}
          >
            {fileBusy ? <Loader2 size={14} className="animate-spin" /> : <ImageUp size={14} />}{" "}
            {fileBusy ? t("readFileBusy") : t("readFile")}
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
          <Button
            onClick={submit}
            disabled={busy || fileBusy || !form.title.trim() || !form.company.trim()}
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}{" "}
            {t("addJob")}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
