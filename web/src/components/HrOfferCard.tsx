import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Loader2, Mail, Phone, UserRound } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody } from "@/components/ui";
import { useT } from "@/i18n";
import type { JobDetail } from "@/types";

/**
 * The people you know at this employer, and their address as an *offer*.
 *
 * The same shape as the JD's own `apply_email` offer in the Add-job form, and
 * for the same reason: pressing the button fills `apply_target`, and nothing is
 * ever sent by filling a field. A wrong address here would mail your CV to a
 * stranger, so the address is always shown in full beside the button — you
 * approve the string you can read, not a name that stands for one.
 *
 * Rendered only when there is somebody on file. A card that says "nobody here"
 * on all 216 jobs is noise; the place to add a contact is /companies, which the
 * link at the foot of the card goes to.
 */
export function HrOfferCard({ job, onChanged }: { job: JobDetail; onChanged: () => void }) {
  const t = useT("companies");
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Same guard as everywhere else that fires a mutation from a click: two
  // clicks in one tick both read the pre-render state (web/src/CLAUDE.md).
  const running = useRef(false);

  if (job.hr_contacts.length === 0) return null;

  async function use(contactId: number, email: string) {
    if (running.current) return;
    running.current = true;
    setBusy(contactId);
    setError(null);
    try {
      await api.patchJob(job.id, { apply_target: email });
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("contactFailed"));
    } finally {
      running.current = false;
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardBody className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="inline-flex items-center gap-2 font-display text-sm font-semibold">
            <UserRound size={15} /> {t("offerTitle", { company: job.company })}
          </h2>
          {job.company_id !== null && (
            <Link to="/companies" className="text-xs text-accent hover:underline">
              {t("offerManage")}
            </Link>
          )}
        </div>

        <div className="flex flex-col gap-2">
          {job.hr_contacts.map((contact) => {
            // The already-selected address gets a tick instead of a button:
            // pressing "use" on the value that is already there teaches nothing
            // and looks like it did something.
            //
            // The channel is part of "already selected", not decoration. A row
            // holding an email address on a `portal`/`external` channel is the
            // broken state this card exists to avoid — applying would hand you
            // an address to "open" — and matching on the address alone would
            // show it a tick and offer no way back.
            const current =
              !!contact.email &&
              job.apply_target === contact.email &&
              job.apply_channel === "email";
            return (
              <div
                key={contact.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2 text-sm"
              >
                <span className="font-medium text-ink">{contact.name}</span>
                {contact.email ? (
                  <span className="inline-flex items-center gap-1 font-mono text-xs text-ink-muted">
                    <Mail size={12} /> {contact.email}
                  </span>
                ) : (
                  <span className="text-xs text-ink-muted">{t("offerNoEmail")}</span>
                )}
                {contact.phone && (
                  <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
                    <Phone size={12} /> {contact.phone}
                  </span>
                )}
                {contact.note && <span className="text-xs text-ink-muted">{contact.note}</span>}
                {contact.email &&
                  (current ? (
                    <span className="ml-auto inline-flex items-center gap-1 text-xs text-good">
                      <Check size={13} /> {t("offerUse")}
                    </span>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="ml-auto"
                      disabled={busy !== null}
                      onClick={() => use(contact.id, contact.email!)}
                    >
                      {busy === contact.id ? <Loader2 size={13} className="animate-spin" /> : null}{" "}
                      {t("offerUse")}
                    </Button>
                  ))}
              </div>
            );
          })}
        </div>

        <p className="text-xs leading-relaxed text-ink-muted">
          {error ? <span className="text-critical">{error}</span> : t("offerHint")}
        </p>
      </CardBody>
    </Card>
  );
}
