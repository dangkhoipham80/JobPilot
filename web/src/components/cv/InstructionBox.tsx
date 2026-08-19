import { useState } from "react";
import { Sparkles, TriangleAlert } from "lucide-react";
import { Button, Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { isActive } from "@/hooks/useTask";
import type { Task } from "@/types";

const EXAMPLES = [
  "Rewrite my summary to lead with backend work",
  "Merge the last two bullets of my ACME job",
  "Add a project: JobPilot, a job crawler I built with FastAPI and React",
];

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
            <Sparkles size={14} className="text-accent" /> Ask for a change
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
          placeholder="Describe the change in your own words…"
          className="w-full resize-y rounded-lg border bg-surface px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-muted focus:border-accent disabled:opacity-60"
        />

        <p className="mt-2 text-xs leading-relaxed text-ink-muted">
          New facts have to come from <span className="text-ink">your</span> words. Anything the
          agent cannot trace back to this box or to the CV — an extra tool, a number you did not
          give — is refused, so state the details you want on the CV.
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button onClick={send} disabled={!text.trim() || busy}>
            {busy ? task?.progress || "Working…" : "Apply to Master CV"}
          </Button>
          {!busy && !text && (
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => setText(ex)}
                  className="rounded-md border px-2 py-1 text-[11px] text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
                >
                  {ex}
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
              <p className="font-medium text-ink">Refused — nothing was changed.</p>
              <p className="mt-1 text-ink-muted">{task.error}</p>
              {task.error_kind === "GuardrailViolation" && (
                <p className="mt-1.5 text-ink-muted">
                  This is the anti-fabrication guard, not a crash. Say the missing detail in your
                  own words and it will go through.
                </p>
              )}
            </div>
          </div>
        )}

        {/* A round that changed nothing is a success, not a failure: refusing to
            invent the detail you didn't give is the correct answer. But it must
            not look like the button did nothing, so it is stated. */}
        {task?.status === "done" && task.result?.changed === false && (
          <p className="mt-3 rounded-lg border bg-surface-2 p-3 text-xs leading-relaxed text-ink-muted">
            <span className="text-ink">Nothing changed — no new version.</span> The agent would
            have had to invent something to do this.
          </p>
        )}

        {task?.status === "done" && task.result?.note ? (
          <p className="mt-3 rounded-lg border bg-surface-2 p-3 text-xs leading-relaxed text-ink-muted">
            <span className="text-ink">The agent noted:</span> {String(task.result.note)}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
