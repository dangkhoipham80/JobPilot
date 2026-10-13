import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Code2, LayoutList, Plus, Save, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useTask } from "@/hooks/useTask";
import { useClampPage, usePaging } from "@/hooks/usePaging";
import { Pagination } from "@/components/Pagination";
import { Button, Card, CardBody, Select, Skeleton } from "@/components/ui";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import { AtsPanel } from "@/components/cv/AtsPanel";
import { MarkupLegend } from "@/components/cv/fields";
import { HeaderEditor } from "@/components/cv/HeaderEditor";
import { ImportBox, releaseDraft, type ImportedDraft } from "@/components/cv/ImportBox";
import { InstructionBox } from "@/components/cv/InstructionBox";
import { PdfPreview } from "@/components/cv/PdfPreview";
import { RawLatexEditor } from "@/components/cv/RawLatexEditor";
import { SectionEditor } from "@/components/cv/SectionEditor";
import { TemplatePicker } from "@/components/cv/TemplatePicker";
import { VersionHistory } from "@/components/cv/VersionHistory";
import { DiffPanel } from "@/components/review/DiffPanel";
import type { AtsReport, CvDocument, CvSection, CvSectionType, CvVersionDiff } from "@/types";

// The `title` here lands in the CV and is rendered into the PDF, so it is CV
// content, not UI copy: it stays in English in both languages, same as every
// other word the user typed. Rename it in the editor to change it.
const NEW_SECTION: Record<CvSectionType, () => CvSection> = {
  paragraph: () => ({ type: "paragraph", key: "summary", title: "Summary", enabled: true, text: "", small: true }),
  bullets: () => ({ type: "bullets", key: "skills", title: "Skills", enabled: true, items: [] }),
  education: () => ({ type: "education", key: "education", title: "Education", enabled: true, entries: [] }),
  experience: () => ({ type: "experience", key: "experience", title: "Work Experience", enabled: true, entries: [] }),
  projects: () => ({ type: "projects", key: "projects", title: "Projects", enabled: true, entries: [] }),
};

/**
 * CV Studio (PLAN.md §5.6.1). The structured JSON is the source of truth: edits
 * stay local until Save, which appends a new version; Compile renders that
 * version to PDF with tectonic.
 */
export function CvStudio({ version: wsVersion }: { version: number }) {
  // /cv edits the Master CV; /cv/<job id> edits that job's tailored fork.
  const { scope = "master" } = useParams();
  const t = useT("cv");
  const tc = useT("common");
  const { data, loading, error, refetch } = useApi(() => api.cv(scope), [scope]);

  const [draft, setDraft] = useState<CvDocument | null>(null);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [savedVersion, setSavedVersion] = useState(0);

  const [mode, setMode] = useState<"fields" | "latex">("fields");
  const [compiling, setCompiling] = useState(false);
  const [compiledAt, setCompiledAt] = useState(0);
  const [pages, setPages] = useState<number | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);
  // undefined = never compiled this session; null = compiled but not checked.
  const [ats, setAts] = useState<AtsReport | null | undefined>(undefined);

  // A draft read from an uploaded file (Master only). It lives in `draft` like
  // any other unsaved edit; this only remembers that it came from a file, so
  // the card can keep saying so — and keep the originals one click away — for
  // as long as it is unsaved.
  //
  // `snapshot` is the editor's document exactly as the reading left it, which
  // is what tells "still the file's words" from "the file's words plus an
  // hour of the user's corrections" — the second must never be overwritten by
  // another import without a word. `same` is settled once, at that moment:
  // the reading matched the saved CV, so there was never a draft to discard.
  const [imported, setImported] = useState<{
    draft: ImportedDraft;
    snapshot: string;
    same: boolean;
  } | null>(null);
  // A reading that came back after the editor had moved on. A read takes a
  // minute; people type in a minute. Held and offered, never applied — the
  // same bargain `editSkippedVersion` strikes for an agent edit.
  const [heldImport, setHeldImport] = useState<ImportedDraft | null>(null);
  // What a read that is in flight needs to know when it lands, and cannot get
  // from the closure it was started in: that render is a minute stale by then,
  // and its card may have unmounted. Refs, so the landing reads the present.
  const scopeEpoch = useRef(0);
  const draftRef = useRef<CvDocument | null>(null);
  const savedRef = useRef<CvDocument | null>(null);
  const importStart = useRef<{ epoch: number; editor: string } | null>(null);
  const importedRef = useRef<ImportedDraft | null>(null);
  const mounted = useRef(true);

  // Adopt the server document whenever a different version arrives: on first
  // load, on a scope change, and after save()/rollback() -- all three are the
  // user asking for exactly this. Guarding this effect on "dirty" broke
  // Restore: rollback() appends a version and refetches, and a blanket guard
  // made that refetch a silent no-op whenever the user had unsaved edits, so
  // the History row and header version moved but the editor never did.
  // The one case this must NOT do is the edit-landing effect below adopting
  // *without asking* -- that guard lives there instead, narrowly, via
  // `dirtyRef` (web/src/CLAUDE.md: guard must be useRef, not state, so the
  // effect reads the current flag without re-running on every keystroke).
  const dirtyRef = useRef(false);
  useEffect(() => {
    if (!data) return;
    setDraft(data.document);
    setSavedVersion(data.version);
    // Whatever was read from a file is no longer what the editor shows: it was
    // either just saved (and is now `data`) or just replaced by a restore.
    setImported(null);
  }, [data]);

  // The object URLs behind "Original:" belong to the draft on screen. Owned
  // here rather than in ImportBox because that card unmounts on the LaTeX tab
  // while the draft survives it — revoking there would leave dead links on return.
  useEffect(() => {
    const held = imported?.draft;
    return () => {
      if (held) releaseDraft(held);
    };
  }, [imported]);
  // ...unless the held reading was just *loaded*: it is then the draft on
  // screen, under the same object, and releasing it here killed the "Original"
  // link on exactly the path where the user most needs to compare. Caught in
  // review, in a browser — the first fix for landings created this path.
  useEffect(() => {
    return () => {
      if (heldImport && importedRef.current !== heldImport) releaseDraft(heldImport);
    };
  }, [heldImport]);
  importedRef.current = imported?.draft ?? null;
  // A read can outlive the page: leave CV Studio mid-read and its promise still
  // resolves, into nothing. That landing must give its files back.
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  draftRef.current = draft;
  savedRef.current = data?.document ?? null;

  // The installed set never changes while the page is open, so this is fetched
  // once per mount rather than tied to scope/version.
  const templates = useApi(() => api.cvTemplates(), []);

  // Edit-by-instruction (Master only). The task is followed rather than awaited:
  // it is a model call plus a guard round, which is seconds, not milliseconds.
  const [editTaskId, setEditTaskId] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const editTask = useTask(editTaskId, wsVersion);
  /** Version the document was on when the edit was queued, for the diff after. */
  const editBase = useRef<number>(0);
  /** Which task's landing this effect has already acted on -- `editTask` stays
   * "done" in state for the rest of the session, so anything that makes the
   * effect below re-run (scope changing back to "master", `refetch`'s identity
   * changing with it) would otherwise resurrect the same banner/diff for a
   * task that already landed once, using now-stale `editBase`/dirty state. */
  const handledEditTaskId = useRef<string | null>(null);

  const versionPaging = usePaging("cv-versions");
  const versions = useApi(
    () => api.cvVersions(scope, { limit: versionPaging.size, offset: versionPaging.offset }),
    [scope, savedVersion, wsVersion, versionPaging.size, versionPaging.offset],
  );
  useClampPage(versions.data?.total, versionPaging);

  // Which pair the History card asked to compare. Versions are immutable, so
  // this is deliberately not refetched on save — the diff on screen stays true.
  const [compare, setCompare] = useState<{ base: number; target: number } | null>(null);
  const diff = useApi(
    () => (compare ? api.cvDiff(scope, compare.base, compare.target) : Promise.resolve(null)),
    [scope, compare?.base, compare?.target],
  );
  // A compare pinned to versions of the CV you just navigated away from would
  // be captioned with the new scope's name.
  useEffect(() => {
    setCompare(null);
    setEditSkippedVersion(null);
    setImported(null);
    setHeldImport(null);
    // Any read still in flight was started for the CV we just left.
    scopeEpoch.current += 1;
  }, [scope]);

  const dirty = useMemo(
    () => !!draft && !!data && JSON.stringify(draft) !== JSON.stringify(data.document),
    [draft, data],
  );
  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty]);
  /** The editor still holds a file's reading untouched — safe to replace. */
  const pristineImport = useMemo(
    () => !!imported && !!draft && JSON.stringify(draft) === imported.snapshot,
    [draft, imported],
  );

  /** A version the agent produced while the editor had unsaved edits — not
   * pulled in automatically, so it doesn't get silently overwritten. */
  const [editSkippedVersion, setEditSkippedVersion] = useState<number | null>(null);

  const askForEdit = useCallback(
    async (instruction: string) => {
      setEditError(null);
      setEditSkippedVersion(null);
      editBase.current = savedVersion;
      try {
        const task = await api.editMasterCv(instruction);
        setEditTaskId(task.id);
      } catch (e) {
        setEditError(e instanceof ApiError ? e.message : t("editStartFailed"));
      }
    },
    [scope, savedVersion, t],
  );

  // When an edit lands, pull the new version in and put the diff on screen --
  // unless the editor has unsaved edits of the user's own right now, in which
  // case pulling it in would discard those silently (this is the one place
  // that reads dirtyRef; the general "adopt the server document" effect above
  // must stay unguarded, or Restore breaks the same way). The diff is opened
  // either way: it comes from `cvDiff`, not from `draft`, so it stays accurate
  // even while the editor keeps showing the user's own in-progress version.
  //
  // Gated on `changed`, not just a version number: a no-op round (the agent
  // declined an ambiguous instruction) reports the *current* version, which is
  // truthy and > 0 same as a real one, and would otherwise pop a banner
  // claiming the agent saved something it explicitly didn't.
  //
  // Gated on scope === "master" too: editing by instruction only ever targets
  // the Master CV (InstructionBox only renders there), but the task can still
  // be in flight after the user navigates to a job's tailored scope, and this
  // effect reads `scope` fresh each run -- without the guard it would refetch,
  // open a compare, or bank a "load vN" offer against the wrong CV entirely.
  //
  // Latched by `handledEditTaskId`: the guards above stop wrong-scope runs but
  // not *stale* ones -- `editTaskId` and its "done" result sit in state for the
  // rest of the session, so navigating away and back to "master" re-runs this
  // effect (scope is a dep, and `refetch`'s identity moves with it) and would
  // otherwise redo everything against `editBase`/`dirtyRef` values that no
  // longer describe the current moment. Only a fresh `editTaskId` (a new
  // instruction) clears the latch.
  //
  // `editTask.id !== editTaskId` is not redundant with the above: `useTask`
  // does not reset its `task` state to null when `taskId` changes, only when
  // it goes null -- so there is a real commit, right after a second
  // instruction is submitted, where `editTaskId` already names the new task
  // but `editTask` still holds the *previous* task's "done" result. Without
  // this check that stale-but-"done" object burns the latch for the new id
  // before the new id's own result ever arrives, and the second (and every
  // later) instruction's landing is silently swallowed.
  useEffect(() => {
    if (scope !== "master") return;
    if (editTask?.status !== "done") return;
    if (!editTaskId || editTask.id !== editTaskId) return;
    if (handledEditTaskId.current === editTaskId) return;
    handledEditTaskId.current = editTaskId;
    const version = Number(editTask.result?.version) || 0;
    const changed = editTask.result?.changed !== false && version > editBase.current;
    if (!changed) return;
    if (dirtyRef.current) {
      setEditSkippedVersion(version);
    } else {
      refetch();
    }
    setCompare({ base: editBase.current, target: version });
  }, [scope, editTaskId, editTask?.id, editTask?.status, editTask?.result?.version, editTask?.result?.changed, refetch]);

  // Deliberately just a refetch, not a fetch of that exact version: the common
  // case is that vN is still HEAD (nothing else has appended since), and
  // refetch() feeds the general "adopt the server document" effect above,
  // which then sets draft AND savedVersion together so `dirty` correctly goes
  // back to false. Fetching vN's content directly and only calling setDraft()
  // was tried and is worse -- it leaves savedVersion/data pointing at the
  // pre-edit version forever, so `dirty` never clears and Save re-appends a
  // duplicate of vN on every click. The rarer race (something else moved HEAD
  // past vN before this runs) just loads that newer real version instead,
  // which is a real, honest state -- unlike the guaranteed-wrong one above.
  const loadSkippedEdit = useCallback(() => {
    setEditSkippedVersion(null);
    refetch();
  }, [refetch]);

  const save = useCallback(async () => {
    if (!draft) return;
    setSaving(true);
    setActionError(null);
    setEditSkippedVersion(null);
    try {
      const res = await api.saveCv(scope, draft);
      setSavedVersion(res.version);
      await refetch();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : t("saveFailed"));
    } finally {
      setSaving(false);
    }
  }, [draft, scope, refetch, t]);

  const compile = useCallback(async () => {
    setCompiling(true);
    setBuildError(null);
    try {
      const res = await api.compileCv(scope);
      setPages(res.pages);
      setAts(res.ats);
      setCompiledAt(Date.now());
    } catch (e) {
      setBuildError(e instanceof Error ? e.message : t("compileFailed"));
      setPages(null);
      setAts(undefined);
    } finally {
      setCompiling(false);
    }
  }, [scope, t]);

  const rollback = useCallback(
    async (target: number) => {
      setActionError(null);
      setEditSkippedVersion(null);
      try {
        const res = await api.rollbackCv(scope, target);
        setSavedVersion(res.version);
        await refetch();
      } catch (e) {
        setActionError(e instanceof ApiError ? e.message : t("restoreFailed"));
      }
    },
    [scope, refetch, t],
  );

  if (loading && !draft) return <StudioSkeleton />;
  if (error) return <Card><CardBody className="text-sm text-critical">{error}</CardBody></Card>;
  if (!draft) return null;

  // The reading replaces the editor's text and nothing else: the template and
  // theme on screen are the user's choice of look, which a file cannot have an
  // opinion about (and the endpoint returns the defaults for both).
  //
  // Everything from here to `discardImport` reads refs, not `draft`/`scope`:
  // `landImport` is called by a promise that was created a minute ago, through
  // whatever version of these functions existed then.
  const applyImport = (next: ImportedDraft) => {
    const current = draftRef.current;
    if (!current) return;
    const document = { ...next.result.document, template: current.template, theme: current.theme };
    const snapshot = JSON.stringify(document);
    setActionError(null);
    setHeldImport(null);
    setDraft(document);
    setImported({ draft: next, snapshot, same: snapshot === JSON.stringify(savedRef.current) });
  };
  const startImport = () => {
    setHeldImport(null);
    importStart.current = {
      epoch: scopeEpoch.current,
      editor: JSON.stringify(draftRef.current),
    };
  };
  const landImport = (next: ImportedDraft) => {
    const started = importStart.current;
    // The user left for another CV while the file was being read. Dropping the
    // result is the only safe answer: the editor now belongs to a tailored CV,
    // and a reading poured into it would be one click from being saved as that
    // job's CV — the thing the endpoint itself refuses with a 400.
    if (!mounted.current || !started || started.epoch !== scopeEpoch.current) {
      releaseDraft(next);
      return;
    }
    // The user typed while the file was being read. Their edits win; the
    // reading waits to be asked for.
    if (JSON.stringify(draftRef.current) !== started.editor) {
      setHeldImport(next);
      return;
    }
    applyImport(next);
  };
  const discardImport = () => {
    // A reading that matched the saved CV left nothing to discard — and any
    // difference in the editor since then is the user's own typing.
    if (data && imported && !imported.same) setDraft(data.document);
    setImported(null);
  };

  const setSections = (sections: CvSection[]) => setDraft({ ...draft, sections });
  const moveSection = (i: number, delta: number) => {
    const next = [...draft.sections];
    const j = i + delta;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    setSections(next);
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">CV Studio</h1>
          <p className="text-sm text-ink-muted">
            {scope === "master" ? t("masterCv") : t("tailoredScope", { scope })} · v{savedVersion}
            {dirty && <span className="ml-2 text-accent">{t("unsaved")}</span>}
            {/* Said here too, not only inside the LaTeX tab: while an override
                is in force these fields don't reach the PDF, and finding that
                out from a PDF that ignored your edits is the bad way. */}
            {data?.tex_override && (
              <span className="ml-2 text-accent">{t("rawLatexActive")}</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {actionError && <span className="text-sm text-critical">{actionError}</span>}
          <ModeSwitch mode={mode} onChange={setMode} />
          {mode === "fields" && (
            <Button onClick={save} disabled={!dirty || saving}>
              <Save size={15} /> {saving ? tc("saving") : t("saveVersion")}
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_460px] 2xl:grid-cols-[minmax(0,1fr)_620px]">
        {/* Editor */}
        <div className="flex min-w-0 flex-col gap-4">
          {compare && (
            <VersionCompare
              base={compare.base}
              target={compare.target}
              state={diff}
              onClose={() => setCompare(null)}
            />
          )}
          {mode === "latex" ? (
            <RawLatexEditor
              scope={scope}
              version={savedVersion}
              onSaved={() => {
                setEditSkippedVersion(null);
                setSavedVersion((v) => v + 1);
                refetch();
              }}
            />
          ) : (
            <>
              <MarkupLegend />
              {scope === "master" && (
                <ImportBox
                  imported={imported?.draft ?? null}
                  unchanged={imported?.same ?? false}
                  held={heldImport}
                  // Unsaved edits are the user's own typing unless the editor
                  // still holds a reading exactly as it arrived; an import
                  // over anything else would erase work without a trace.
                  blocked={dirty && !pristineImport}
                  onStart={startImport}
                  onDraft={landImport}
                  onLoadHeld={() => heldImport && applyImport(heldImport)}
                  onDropHeld={() => setHeldImport(null)}
                  onDiscard={discardImport}
                />
              )}
              {scope === "master" && (
                <InstructionBox task={editTask} error={editError} onSubmit={askForEdit} />
              )}
              {editSkippedVersion != null && (
                <Card>
                  <CardBody className="flex items-center justify-between gap-3 text-xs text-ink-muted">
                    <span>
                      {t("skippedLead")} <span className="text-ink">v{editSkippedVersion}</span>{" "}
                      {t("skippedBody", { version: editSkippedVersion })}
                    </span>
                    <Button size="sm" variant="outline" onClick={loadSkippedEdit}>
                      {t("loadVersion", { version: editSkippedVersion })}
                    </Button>
                  </CardBody>
                </Card>
              )}
              <TemplatePicker
                templates={templates.data?.templates ?? null}
                error={templates.error}
                value={draft.template}
                onChange={(template) => setDraft({ ...draft, template })}
              />
              <HeaderEditor
                header={draft.header}
                theme={draft.theme}
                template={draft.template}
                onHeader={(header) => setDraft({ ...draft, header })}
                onTheme={(theme) => setDraft({ ...draft, theme })}
              />

              {draft.sections.map((section, i) => (
                <SectionEditor
                  key={`${section.key}-${i}`}
                  section={section}
                  disableUp={i === 0}
                  disableDown={i === draft.sections.length - 1}
                  onMove={(delta) => moveSection(i, delta)}
                  onChange={(next) =>
                    setSections(draft.sections.map((s, j) => (j === i ? next : s)))
                  }
                  onRemove={() => setSections(draft.sections.filter((_, j) => j !== i))}
                />
              ))}

              <AddSection onAdd={(type) => setSections([...draft.sections, NEW_SECTION[type]()])} />
            </>
          )}
        </div>

        {/* Right rail */}
        <div className="flex flex-col gap-4 xl:sticky xl:top-20 xl:self-start">
          <PdfPreview
            scope={scope}
            dirty={dirty}
            compiling={compiling}
            pages={pages}
            error={buildError}
            compiledAt={compiledAt}
            onCompile={compile}
          />
          {ats !== undefined && (
            <Card className="p-4">
              <AtsPanel report={ats} />
            </Card>
          )}
          <VersionHistory
            versions={versions.data?.items ?? null}
            total={versions.data?.total ?? 0}
            current={savedVersion}
            loading={versions.loading}
            busy={saving}
            onRollback={rollback}
            onCompare={(base, target) => setCompare({ base, target })}
            pager={
              <Pagination
                className="mt-3"
                page={versionPaging.page}
                size={versionPaging.size}
                total={versions.data?.total ?? 0}
                onPage={versionPaging.setPage}
                onSize={versionPaging.setSize}
                noun={t("versionsNoun")}
              />
            }
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Version compare. Sits in the editor column rather than the right rail because
 * reading a diff is a full-width job, and while you're reading one you aren't
 * editing. The heading uses the versions the *server* echoed back, not the ones
 * we asked for, so a mislabelled panel can't survive a backend disagreement.
 */
function VersionCompare({
  base,
  target,
  state,
  onClose,
}: {
  base: number;
  target: number;
  state: { data: CvVersionDiff | null; loading: boolean; error: string | null };
  onClose: () => void;
}) {
  const t = useT("cv");
  const tc = useT("common");
  const close = (
    <Button size="sm" variant="ghost" className="h-7 shrink-0 px-2" onClick={onClose}>
      <X size={13} /> {tc("close")}
    </Button>
  );

  if (state.error) {
    return (
      <Card>
        <CardBody className="flex items-center justify-between gap-3 text-sm text-critical">
          {state.error}
          {close}
        </CardBody>
      </Card>
    );
  }
  if (!state.data) {
    return <Skeleton className="h-40" />;
  }

  const { diff } = state.data;
  const same = state.data.base === state.data.target;
  return (
    <div className="flex flex-col gap-2">
      <DiffPanel
        diff={diff}
        title={`v${state.data.base} → v${state.data.target}`}
        action={close}
      />
      {!diff.changed && (
        <p className="px-1 text-xs text-ink-muted">
          {same ? t("compareSame") : t("compareIdentical", { base, target })}
        </p>
      )}
    </div>
  );
}

function ModeSwitch({
  mode,
  onChange,
}: {
  mode: "fields" | "latex";
  onChange: (next: "fields" | "latex") => void;
}) {
  const t = useT("cv");
  const tabs = [
    { id: "fields" as const, label: t("tabFields"), icon: LayoutList },
    { id: "latex" as const, label: t("tabLatex"), icon: Code2 },
  ];
  return (
    <div className="flex items-center gap-0.5 rounded-lg border p-0.5">
      {tabs.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium transition-colors",
            mode === id ? "bg-accent/12 text-ink" : "text-ink-muted hover:bg-surface-2 hover:text-ink",
          )}
        >
          <Icon size={14} /> {label}
        </button>
      ))}
    </div>
  );
}

function AddSection({ onAdd }: { onAdd: (type: CvSectionType) => void }) {
  const t = useT("cv");
  const [type, setType] = useState<CvSectionType>("bullets");
  return (
    <div className="flex items-center gap-2">
      <Select value={type} onChange={(e) => setType(e.target.value as CvSectionType)}>
        <option value="paragraph">{t("typeParagraph")}</option>
        <option value="bullets">{t("typeBullets")}</option>
        <option value="education">{t("typeEducation")}</option>
        <option value="experience">{t("typeExperience")}</option>
        <option value="projects">{t("typeProjects")}</option>
      </Select>
      <Button variant="outline" size="sm" onClick={() => onAdd(type)}>
        <Plus size={14} /> {t("addSection")}
      </Button>
    </div>
  );
}

function StudioSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_460px] 2xl:grid-cols-[minmax(0,1fr)_620px]">
      <div className="flex flex-col gap-4">
        <Skeleton className="h-56" />
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
      </div>
      <Skeleton className="h-[600px]" />
    </div>
  );
}
