import { useState } from "react";
import { Sparkles, TriangleAlert } from "lucide-react";
import { Button, Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { isActive } from "@/hooks/useTask";
import { useT } from "@/i18n";
import type { Task } from "@/types";

/** Prefill chips. Deliberately English in both languages — the text lands in
 *  the textarea and then on the CV verbatim, so it follows the CV's language,
 *  not the UI's. Reasoning in full at `i18n/dict/cv.ts`. */
const EXAMPLES = ["example1", "example2", "example3"] as const;

/**
 * Change the Master CV by describing the change (Master scope only).
 *
 * The copy here is doing real work, not decoration. This is the one place in
 * JobPilot where a model may write a *new* claim onto the CV, and it is allowed
 * to only because the user's own words license it — so the box says that out
 * loud, and says what happens when the words run out. A user who believes the
 * agent can fill in details will write "add my Kafka project" and get a refusal
 * they read as a bug; one who knows it can only repeat them writes the sentence
 * that actually works.
 */
export function InstructionBox({
  task,
  error,
  onSubmit,
}: {
  task: Task | null;
  error: string | null;
  onSubmit: (instruction: string) => void;
}) {
  const t = useT("cv");
  const [text, setText] = useState("");
  const busy = isActive(task);

  const send = () => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    onSubmit(trimmed);
    setText("");
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="inline-flex items-center gap-1.5">
            <Sparkles size={14} className="text-accent" /> {t("askForChange")}
          </span>
        </CardTitle>
      </CardHeader>
      <CardBody className="pt-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
          }}
          rows={3}
          disabled={busy}
          placeholder={t("instructionPlaceholder")}
          className="w-full resize-y rounded-lg border bg-surface px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-muted focus:border-accent disabled:opacity-60"
        />

        <p className="mt-2 text-xs leading-relaxed text-ink-muted">
          {t("factsLead")} <span className="text-ink">{t("factsEmphasis")}</span> {t("factsRest")}
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button onClick={send} disabled={!text.trim() || busy}>
            {/* `task.progress` is a backend log line, shown as the worker wrote it. */}
            {busy ? task?.progress || t("working") : t("applyToMaster")}
          </Button>
          {!busy && !text && (
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLES.map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setText(t(key))}
                  className="rounded-md border px-2 py-1 text-[11px] text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
                >
                  {t(key)}
                </button>
              ))}
            </div>
          )}
        </div>

        {error && <p className="mt-3 text-sm text-critical">{error}</p>}

        {task?.status === "failed" && (
          <div className="mt-3 flex gap-2 rounded-lg border border-critical/30 bg-critical/8 p-3">
            <TriangleAlert size={15} className="mt-0.5 shrink-0 text-critical" />
            <div className="text-xs leading-relaxed">
              <p className="font-medium text-ink">{t("refusedTitle")}</p>
              {/* `task.error` is the backend's own message, not UI copy. */}
              <p className="mt-1 text-ink-muted">{task.error}</p>
              {task.error_kind === "GuardrailViolation" && (
                <p className="mt-1.5 text-ink-muted">{t("refusedGuard")}</p>
              )}
            </div>
          </div>
        )}

        {/* A round that changed nothing is a success, not a failure: refusing to
            invent the detail you didn't give is the correct answer. But it must
            not look like the button did nothing, so it is stated. */}
        {task?.status === "done" && task.result?.changed === false && (
          <p className="mt-3 rounded-lg border bg-surface-2 p-3 text-xs leading-relaxed text-ink-muted">
            <span className="text-ink">{t("noChangeTitle")}</span> {t("noChangeBody")}
          </p>
        )}

        {task?.status === "done" && task.result?.note ? (
          <p className="mt-3 rounded-lg border bg-surface-2 p-3 text-xs leading-relaxed text-ink-muted">
            {/* The note is the agent's own sentence, passed through verbatim. */}
            <span className="text-ink">{t("agentNoted")}</span> {String(task.result.note)}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
