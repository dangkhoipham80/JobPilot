import { useRef, useState } from "react";
import { Loader2, Mail, Phone, Plus, Trash2, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Input } from "@/components/ui";
import { useT } from "@/i18n";
import type { CompanyDetail, HrContact } from "@/types";

/**
 * The people on file at one employer, with the form to add another.
 *
 * Editing is deliberately shallow — a contact is four short fields and the
 * whole record fits on one line, so an inline form beats a modal. Deleting asks
 * first, because a phone number that came off a call is not recoverable from
 * anywhere else in the app.
 */
export function HrContactList({
  company,
  onChanged,
}: {
  company: CompanyDetail;
  onChanged: (next: CompanyDetail) => void;
}) {
  const t = useT("companies");
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", phone: "", email: "", note: "" });
  // A ref, not `busy`: two clicks in the same tick both read the pre-render
  // state and both post, leaving two identical contacts (web/src/CLAUDE.md).
  const running = useRef(false);

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: e.target.value });

  function reset() {
    setForm({ name: "", phone: "", email: "", note: "" });
    setAdding(false);
    setError(null);
  }

  async function save() {
    if (running.current || !form.name.trim()) return;
    running.current = true;
    setBusy(true);
    setError(null);
    try {
      await api.addContact(company.id, {
        name: form.name.trim(),
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        note: form.note.trim() || null,
      });
      // Refetched rather than pushed onto the local list: the counts on the card
      // (`contact_count`) are computed server-side, and a client-side append
      // would leave the number beside the list disagreeing with the list.
      onChanged(await api.company(company.id));
      reset();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("contactFailed"));
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  async function remove(contact: HrContact) {
    if (!confirm(t("confirmDeleteContact", { name: contact.name, company: company.name }))) return;
    setError(null);
    try {
      onChanged(await api.deleteContact(company.id, contact.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("contactFailed"));
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {company.contacts.length === 0 && !adding && (
        <p className="text-xs text-ink-muted">{t("noContacts")}</p>
      )}

      {company.contacts.map((contact) => (
        <div
          key={contact.id}
          className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-lg border px-3 py-2 text-sm"
        >
          <span className="font-medium text-ink">{contact.name}</span>
          {contact.email && (
            <a
              href={`mailto:${contact.email}`}
              className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
            >
              <Mail size={12} /> {contact.email}
            </a>
          )}
          {contact.phone && (
            <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
              <Phone size={12} /> {contact.phone}
            </span>
          )}
          {contact.note && <span className="text-xs text-ink-muted">{contact.note}</span>}
          <button
            onClick={() => remove(contact)}
            title={t("deleteContact")}
            aria-label={t("deleteContact")}
            className="ml-auto text-ink-muted hover:text-critical"
          >
            <Trash2 size={13} />
          </button>
        </div>
      ))}

      {adding ? (
        <div className="flex flex-col gap-2 rounded-lg border px-3 py-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <Input placeholder={t("contactName")} value={form.name} onChange={set("name")} autoFocus />
            <Input placeholder={t("contactPhone")} value={form.phone} onChange={set("phone")} />
            <Input placeholder={t("contactEmail")} value={form.email} onChange={set("email")} />
          </div>
          <Input placeholder={t("contactNote")} value={form.note} onChange={set("note")} />
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-ink-muted">
              {error ? <span className="text-critical">{error}</span> : t("contactNoteHint")}
            </span>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={reset}>
                <X size={14} />
              </Button>
              <Button size="sm" onClick={save} disabled={busy || !form.name.trim()}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : null} {t("saveContact")}
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
            <Plus size={14} /> {t("addContact")}
          </Button>
          {error && <span className="text-xs text-critical">{error}</span>}
        </div>
      )}
    </div>
  );
}
