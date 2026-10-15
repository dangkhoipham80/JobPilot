import { useState } from "react";
import { ChevronDown, ChevronRight, Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import { Button, Card, Input } from "@/components/ui";
import { AutoTextarea, BulletList, IconButton, ReorderHandle, TagsField, TextField } from "@/components/cv/fields";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import { parkedBy, type CvEducationEntry, type CvEntry, type CvSection } from "@/types";

const EMPTY_ENTRY: CvEntry = {
  title: "",
  date: "",
  url: null,
  items: [],
  role: null,
  tech_stack: [],
  tags: [],
};
const EMPTY_EDUCATION: CvEducationEntry = {
  degree: "",
  institution: "",
  location: "",
  date: "",
  items: [],
};

/** Section type → key in the `cv` namespace, resolved at render. */
const TYPE_LABEL = {
  paragraph: "typeParagraph",
  bullets: "typeBullets",
  education: "typeEducation",
  experience: "typeExperience",
  projects: "typeProjects",
} as const satisfies Record<CvSection["type"], string>;

/**
 * "3 entries" / "120 words" for the collapsed header.
 *
 * A component rather than a helper so it can call `useT` itself: a plain
 * function would have to take the translator as an argument, which loses the
 * compile-time key checking that is the point of the typed dictionary.
 */
function SectionSummary({ section }: { section: CvSection }) {
  const t = useT("cv");
  const count = (n: number, one: "wordsOne" | "itemsOne" | "entriesOne") => {
    const many = one.replace("One", "Many") as "wordsMany" | "itemsMany" | "entriesMany";
    return t(n === 1 ? one : many, { n });
  };

  let text: string;
  switch (section.type) {
    case "paragraph":
      text = count(section.text.trim().split(/\s+/).filter(Boolean).length, "wordsOne");
      break;
    case "bullets":
      text = count(section.items.length, "itemsOne");
      break;
    default:
      text = count(section.entries.length, "entriesOne");
  }
  return <span className="shrink-0 text-xs text-ink-muted">{text}</span>;
}

export function SectionEditor({
  section,
  onChange,
  onRemove,
  onMove,
  disableUp,
  disableDown,
  hiddenTags,
}: {
  section: CvSection;
  onChange: (s: CvSection) => void;
  onRemove: () => void;
  onMove: (delta: number) => void;
  disableUp: boolean;
  disableDown: boolean;
  /** The document's `hidden_tags`, so a parked entry can say so. */
  hiddenTags?: string[];
}) {
  const t = useT("cv");
  // Collapsed by default: six expanded sections make the page ~10,000px tall,
  // which hides the one thing this screen is for — seeing the CV's shape. The
  // collapsed header carries the title, type and item count, so you can tell
  // where to click without opening anything.
  const [open, setOpen] = useState(false);

  return (
    <Card className={cn("group", !section.enabled && "opacity-55")}>
      <div className="flex items-center gap-1 px-3 py-2.5">
        <ReorderHandle
          onUp={() => onMove(-1)}
          onDown={() => onMove(1)}
          disableUp={disableUp}
          disableDown={disableDown}
        />
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          <span className="truncate font-display text-sm font-semibold">{section.title || section.key}</span>
          <span className="shrink-0 rounded border px-1.5 py-px font-mono text-[10px] uppercase tracking-wide text-ink-muted">
            {t(TYPE_LABEL[section.type])}
          </span>
          <SectionSummary section={section} />
        </button>
        <IconButton
          label={section.enabled ? t("hideFromPdf") : t("showInPdf")}
          onClick={() => onChange({ ...section, enabled: !section.enabled })}
        >
          {section.enabled ? <Eye size={15} /> : <EyeOff size={15} />}
        </IconButton>
        <IconButton label={t("deleteSection")} onClick={onRemove} danger>
          <Trash2 size={15} />
        </IconButton>
      </div>

      {open && (
        <div className="flex flex-col gap-4 border-t px-5 py-4">
          <div className="grid grid-cols-2 gap-4">
            <TextField
              label={t("sectionTitle")}
              value={section.title}
              onChange={(v) => onChange({ ...section, title: v })}
            />
            <TextField
              label={t("sectionKey")}
              hint={t("sectionKeyHint")}
              value={section.key}
              onChange={(v) => onChange({ ...section, key: v })}
            />
          </div>
          <SectionBody section={section} onChange={onChange} hiddenTags={hiddenTags} />
        </div>
      )}
    </Card>
  );
}

function SectionBody({
  section,
  onChange,
  hiddenTags,
}: {
  section: CvSection;
  onChange: (s: CvSection) => void;
  hiddenTags?: string[];
}) {
  const t = useT("cv");
  switch (section.type) {
    case "paragraph":
      return (
        <AutoTextarea
          value={section.text}
          placeholder={t("summaryPlaceholder")}
          onChange={(text) => onChange({ ...section, text })}
        />
      );

    case "bullets":
      return (
        <div className="flex flex-col gap-2">
          {section.items.map((item, i) => (
            <div key={i} className="group flex items-start gap-1.5">
              <Input
                className="w-44 shrink-0"
                placeholder={t("labelOptional")}
                value={item.label ?? ""}
                onChange={(e) =>
                  onChange({
                    ...section,
                    items: section.items.map((x, j) =>
                      j === i ? { ...x, label: e.target.value || null } : x,
                    ),
                  })
                }
              />
              <AutoTextarea
                value={item.text}
                placeholder="Java, Spring Boot, Docker"
                onChange={(text) =>
                  onChange({
                    ...section,
                    items: section.items.map((x, j) => (j === i ? { ...x, text } : x)),
                  })
                }
              />
              <Input
                className="w-32 shrink-0"
                placeholder={t("datePlaceholder")}
                value={item.date ?? ""}
                onChange={(e) =>
                  onChange({
                    ...section,
                    items: section.items.map((x, j) =>
                      j === i ? { ...x, date: e.target.value || null } : x,
                    ),
                  })
                }
              />
              <IconButton
                label={t("removeItem")}
                danger
                onClick={() => onChange({ ...section, items: section.items.filter((_, j) => j !== i) })}
              >
                <Trash2 size={14} />
              </IconButton>
            </div>
          ))}
          <Button
            variant="ghost"
            size="sm"
            className="self-start"
            onClick={() =>
              onChange({ ...section, items: [...section.items, { label: null, text: "", date: null }] })
            }
          >
            <Plus size={14} /> {t("addItem")}
          </Button>
        </div>
      );

    case "education":
      return (
        <EntryList
          entries={section.entries}
          empty={EMPTY_EDUCATION}
          addLabel={t("addEducation")}
          onChange={(entries) => onChange({ ...section, entries })}
          render={(entry, set) => (
            <>
              <div className="grid grid-cols-2 gap-4">
                <TextField label={t("degree")} value={entry.degree} onChange={(v) => set({ degree: v })} />
                <TextField
                  label={t("institution")}
                  value={entry.institution}
                  onChange={(v) => set({ institution: v })}
                />
                <TextField label={t("location")} value={entry.location} onChange={(v) => set({ location: v })} />
                <TextField
                  label={t("date")}
                  hint={t("dashHint")}
                  value={entry.date}
                  onChange={(v) => set({ date: v })}
                />
              </div>
              <BulletList items={entry.items} onChange={(items) => set({ items })} />
            </>
          )}
        />
      );

    case "experience":
    case "projects":
      return (
        <EntryList
          entries={section.entries}
          empty={EMPTY_ENTRY}
          addLabel={section.type === "projects" ? t("addProject") : t("addRole")}
          onChange={(entries) => onChange({ ...section, entries } as CvSection)}
          muted={(entry) => parkedBy(entry, hiddenTags) !== null}
          render={(entry, set) => (
            <>
              {parkedBy(entry, hiddenTags) && (
                <span className="self-start rounded border border-dashed px-1.5 py-px text-[11px] text-ink-muted">
                  {t("parked", { tag: parkedBy(entry, hiddenTags) ?? "" })}
                </span>
              )}
              <div className="grid grid-cols-2 gap-4">
                <TextField
                  label={t("entryTitle")}
                  value={entry.title}
                  onChange={(v) => set({ title: v })}
                  className="col-span-2"
                />
                <TextField
                  label={t("date")}
                  hint={t("dashHint")}
                  value={entry.date}
                  onChange={(v) => set({ date: v })}
                />
                <TextField
                  label={t("link")}
                  hint={t("optional")}
                  value={entry.url ?? ""}
                  onChange={(v) => set({ url: v || null })}
                />
              </div>
              <BulletList items={entry.items} onChange={(items) => set({ items })} />
              <div className="grid grid-cols-3 gap-4">
                <TextField
                  label={t("role")}
                  hint={t("optional")}
                  value={entry.role ?? ""}
                  onChange={(v) => set({ role: v || null })}
                />
                <TagsField
                  label={t("techStack")}
                  value={entry.tech_stack}
                  onChange={(tech_stack) => set({ tech_stack })}
                />
                <TagsField
                  label={t("entryTags")}
                  hint={t("entryTagsHint")}
                  placeholder="game, school"
                  value={entry.tags ?? []}
                  onChange={(tags) => set({ tags })}
                />
              </div>
            </>
          )}
        />
      );
  }
}

/** Reorderable list of entry cards, shared by education/experience/projects. */
function EntryList<T>({
  entries,
  empty,
  addLabel,
  onChange,
  render,
  muted,
}: {
  entries: T[];
  empty: T;
  addLabel: string;
  onChange: (entries: T[]) => void;
  render: (entry: T, set: (patch: Partial<T>) => void) => React.ReactNode;
  /** Dims an entry the PDF will leave out, the way a hidden section is dimmed. */
  muted?: (entry: T) => boolean;
}) {
  const t = useT("cv");
  const move = (i: number, delta: number) => {
    const next = [...entries];
    const j = i + delta;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };

  return (
    <div className="flex flex-col gap-3">
      {entries.map((entry, i) => (
        <div
          key={i}
          className={cn(
            "group flex items-start gap-1.5 rounded-lg border bg-surface-2/60 p-3",
            muted?.(entry) && "opacity-55",
          )}
        >
          <ReorderHandle
            onUp={() => move(i, -1)}
            onDown={() => move(i, 1)}
            disableUp={i === 0}
            disableDown={i === entries.length - 1}
          />
          <div className="flex min-w-0 flex-1 flex-col gap-3">
            {render(entry, (patch) =>
              onChange(entries.map((x, j) => (j === i ? { ...x, ...patch } : x))),
            )}
          </div>
          <IconButton
            label={t("removeEntry")}
            danger
            onClick={() => onChange(entries.filter((_, j) => j !== i))}
          >
            <Trash2 size={14} />
          </IconButton>
        </div>
      ))}
      <Button
        variant="ghost"
        size="sm"
        className="self-start"
        onClick={() => onChange([...entries, structuredClone(empty)])}
      >
        <Plus size={14} /> {addLabel}
      </Button>
    </div>
  );
}
