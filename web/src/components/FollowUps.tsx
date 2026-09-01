import { useCallback, useState } from "react";
import { BellRing, Check, X } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Card } from "@/components/ui";
import { useT } from "@/i18n";
import type { Application } from "@/types";

/**
 * Applications that have gone quiet long enough to chase.
 *
 * Deliberately a prompt and not an outbox: nothing is sent from here. A
 * follow-up is a message to a person who is deciding about you, and mail that
 * leaves the machine without you seeing it is the one thing the apply rules
 * forbid. So this tells you who to write to and gets out of the way.
 */
export function FollowUps({
  items,
  onChange,
  pager,
  total,
}: {
  items: Application[];
  onChange: () => void;
  /** Rendered under the list. Passed in rather than built here so the page
   *  owns the page state that its refetch already depends on. */
  pager?: React.ReactNode;
  /** How many are due in total, not just on this page — the heading counts
   *  the work, and a page size is not a fact about the work. */
  total?: number;
}) {
  const t = useT("applications");
  const [busy, setBusy] = useState<number | null>(null);

  const act = useCallback(
    async (id: number, what: "sent" | "stop") => {
      setBusy(id);
      try {
        await (what === "sent" ? api.markFollowedUp(id) : api.stopFollowups(id));
        onChange();
      } finally {
        setBusy(null);
      }
    },
    [onChange],
  );

  const count = total ?? items.length;
  if (!count) return null;

  return (
    <Card className="border-caution/40 bg-caution/5 p-4">
      <header className="mb-3 flex items-center gap-2">
        <BellRing size={15} className="shrink-0 text-caution" />
        <h2 className="text-sm font-semibold">
          {t(count > 1 ? "followupsTitle" : "followupsTitleOne", { count })}
        </h2>
      </header>

      <ul className="space-y-2">
        {items.map((a) => (
          <li
            key={a.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
          >
            <div className="min-w-0 flex-1">
              <span className="font-medium">{a.job_title}</span>
              <span className="text-ink-muted"> · {a.company}</span>
              {/* `followup_hint` is written by the backend cadence — data. */}
              <p className="text-xs text-ink-muted">{a.followup_hint}</p>
            </div>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy === a.id}
              onClick={() => act(a.id, "sent")}
              title={t("followedUpTitle")}
            >
              <Check size={13} /> {t("followedUp")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy === a.id}
              onClick={() => act(a.id, "stop")}
              title={t("letItGoTitle")}
            >
              <X size={13} /> {t("letItGo")}
            </Button>
          </li>
        ))}
      </ul>
      {pager}
    </Card>
  );
}
