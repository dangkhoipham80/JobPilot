import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, Check, Loader2, Pencil, Plus, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useClampPage, usePaging } from "@/hooks/usePaging";
import { Pagination } from "@/components/Pagination";
import { HrContactList } from "@/components/HrContactList";
import { Button, Card, CardBody, CardHeader, CardTitle, Input, Select, Skeleton } from "@/components/ui";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import type { CompaniesQuery, Company, CompanyDetail } from "@/types";

/** Value that lags its input, so a search fires once the typing stops. */
function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return settled;
}

/**
 * Every employer in the corpus, and the people you know at them.
 *
 * Rows are provisioned by the write paths, so this page is a *view* of
 * something the app already maintains rather than a form you have to keep fed.
 * That is why the default order is "most applied to": ~150 of the rows here
 * arrived on their own and you have never written to them, and sorting by
 * applications floats the handful you are actually working to the top.
 *
 * A company expands in place instead of navigating. Its contacts and its recent
 * postings are both short, and the reason you open one is almost always to add
 * a phone number and go back to the list.
 */
export function Companies({ version }: { version: number }) {
  const t = useT("companies");
  const paging = usePaging("companies");
  const [q, setQ] = useState("");
  const [order, setOrder] = useState<NonNullable<CompaniesQuery["order"]>>("applied");
  const [withContacts, setWithContacts] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);

  // The box updates on every keystroke; the query does not. Without this,
  // typing an eight-letter employer name fires eight requests, seven of which
  // are answers to questions already abandoned — and they can land out of order.
  const search = useDebounced(q, 250);

  const { reset } = paging;
  // Back to page 1 whenever a *filter* changes. Sitting on page 7 of a search
  // that now has four results is an empty table with no hint why.
  useEffect(() => {
    reset();
  }, [search, order, withContacts, reset]);

  const companies = useApi(
    () =>
      api.companies({
        q: search || undefined,
        with_contacts: withContacts || undefined,
        order,
        limit: paging.size,
        offset: paging.offset,
      }),
    [version, search, order, withContacts, paging.size, paging.offset],
  );
  useClampPage(companies.data?.total, paging);

  const items = companies.data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink-muted">{t("intro")}</p>
      </div>

      <AddCompany onCreated={() => companies.refetch()} />

      <Card>
        <CardHeader className="flex flex-wrap items-center gap-3">
          <CardTitle className="flex items-center gap-2">
            <Building2 size={16} /> {t("title")}
          </CardTitle>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Input
              placeholder={t("search")}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="w-52"
            />
            <Select
              value={order}
              onChange={(e) => setOrder(e.target.value as CompaniesQuery["order"] as never)}
            >
              <option value="applied">{t("orderApplied")}</option>
              <option value="jobs">{t("orderJobs")}</option>
              <option value="name">{t("orderName")}</option>
            </Select>
            <label className="flex items-center gap-1.5 text-xs text-ink-muted">
              <input
                type="checkbox"
                checked={withContacts}
                onChange={(e) => setWithContacts(e.target.checked)}
                className="accent-accent"
              />
              {t("onlyWithContacts")}
            </label>
          </div>
        </CardHeader>
        <CardBody className="flex flex-col gap-2">
          {companies.loading && !companies.data && (
            <>
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </>
          )}
          {companies.error && <p className="text-sm text-critical">{t("loadFailed")}</p>}
          {companies.data && items.length === 0 && (
            <p className="py-6 text-center text-sm text-ink-muted">
              {search || withContacts ? t("emptyFiltered") : t("empty")}
            </p>
          )}

          {items.map((company) => (
            <CompanyRow
              key={company.id}
              company={company}
              open={openId === company.id}
              onToggle={() => setOpenId(openId === company.id ? null : company.id)}
              onChanged={() => companies.refetch()}
            />
          ))}

          {companies.data && companies.data.total > 0 && (
            <Pagination
              page={paging.page}
              size={paging.size}
              total={companies.data.total}
              onPage={paging.setPage}
              onSize={paging.setSize}
              noun={t("noun")}
            />
          )}
        </CardBody>
      </Card>
    </div>
  );
}

/** One row, and everything about that employer when it is expanded. */
function CompanyRow({
  company,
  open,
  onToggle,
  onChanged,
}: {
  company: Company;
  open: boolean;
  onToggle: () => void;
  onChanged: () => void;
}) {
  const t = useT("companies");
  // Only fetched when opened. The list row already carries the three counts, so
  // an unopened company costs nothing extra — with ~150 rows, eagerly loading
  // every contact list would be 150 requests to render a page nobody scrolled.
  const detail = useApi(() => (open ? api.company(company.id) : Promise.resolve(null)), [open, company.id]);
  const [local, setLocal] = useState<CompanyDetail | null>(null);
  const shown = local ?? detail.data;

  useEffect(() => {
    setLocal(null);
  }, [company.id, open]);

  return (
    <div className={cn("rounded-lg border", open && "border-accent/40 bg-surface-2/40")}>
      <button
        onClick={onToggle}
        className="flex w-full flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2.5 text-left"
      >
        <span className="font-medium text-ink">{company.name}</span>
        <span className="text-xs text-ink-muted">{t(company.job_count === 1 ? "jobsCountOne" : "jobsCount", { count: company.job_count })}</span>
        {company.applied_count > 0 && (
          <span className="rounded-md bg-accent/10 px-1.5 py-0.5 text-[11px] font-medium text-accent">
            {t("appliedCount", { count: company.applied_count })}
          </span>
        )}
        {company.contact_count > 0 && (
          <span className="text-xs text-ink-muted">
            {t(company.contact_count === 1 ? "contactsCountOne" : "contactsCount", {
              count: company.contact_count,
            })}
          </span>
        )}
        {/* The fold, said out loud. It is the one thing on this page a person
            might disagree with — two spellings merged into one row — and a
            merge you cannot see is a merge you cannot argue with. */}
        <span className="ml-auto font-mono text-[11px] text-ink-muted">
          {t("foldedAs", { key: company.normalized_name })}
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-4 border-t px-3 py-3">
          {detail.loading && !shown && <Skeleton className="h-16 w-full" />}
          {shown && (
            <>
              <RenameCompany company={shown} onRenamed={(next) => { setLocal(next); onChanged(); }} />

              <section className="flex flex-col gap-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  {t("contacts")}
                </h3>
                <HrContactList
                  company={shown}
                  onChanged={(next) => {
                    setLocal(next);
                    onChanged();
                  }}
                />
              </section>

              <section className="flex flex-col gap-1.5">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  {t("postings")}
                </h3>
                {shown.jobs.length === 0 && <p className="text-xs text-ink-muted">{t("noPostings")}</p>}
                {shown.jobs.map((job) => (
                  <Link
                    key={job.id}
                    to={`/jobs/${job.id}`}
                    className="flex flex-wrap items-baseline gap-x-2 text-sm text-ink hover:text-accent"
                  >
                    <span>{job.title}</span>
                    <span className="text-xs text-ink-muted">{job.source}</span>
                    {job.location && <span className="text-xs text-ink-muted">{job.location}</span>}
                  </Link>
                ))}
                {shown.jobs_truncated && (
                  <p className="text-xs text-ink-muted">
                    {t("postingsTruncated", { count: shown.jobs.length })}
                  </p>
                )}
              </section>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** Rename an employer. Cosmetic — identity is the fold, which is not editable. */
function RenameCompany({
  company,
  onRenamed,
}: {
  company: CompanyDetail;
  onRenamed: (next: CompanyDetail) => void;
}) {
  const t = useT("companies");
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(company.name);
  const [error, setError] = useState<string | null>(null);
  const running = useRef(false);

  async function save() {
    if (running.current || !name.trim()) return;
    running.current = true;
    setError(null);
    try {
      onRenamed(await api.renameCompany(company.id, name.trim()));
      setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("renameFailed"));
    } finally {
      running.current = false;
    }
  }

  if (!editing) {
    return (
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => { setName(company.name); setEditing(true); }}>
          <Pencil size={13} /> {t("rename")}
        </Button>
        {error && <span className="text-xs text-critical">{error}</span>}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input value={name} onChange={(e) => setName(e.target.value)} className="w-64" autoFocus />
      <Button size="sm" onClick={save} disabled={!name.trim()}>
        <Check size={14} />
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
        <X size={14} />
      </Button>
      <span className="text-xs text-ink-muted">{error ?? t("renameHint")}</span>
    </div>
  );
}

/** Track an employer before any posting from them has landed. */
function AddCompany({ onCreated }: { onCreated: () => void }) {
  const t = useT("companies");
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const running = useRef(false);

  async function save() {
    if (running.current || !name.trim()) return;
    running.current = true;
    setBusy(true);
    setError(null);
    try {
      await api.createCompany(name.trim());
      setName("");
      setOpen(false);
      onCreated();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("addFailed"));
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div>
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          <Plus size={14} /> {t("add")}
        </Button>
      </div>
    );
  }

  return (
    <Card>
      <CardBody className="flex flex-wrap items-center gap-2">
        <Input
          placeholder={t("addPlaceholder")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-64"
          autoFocus
        />
        <Button size="sm" onClick={save} disabled={busy || !name.trim()}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} {t("add")}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => { setOpen(false); setError(null); }}>
          <X size={14} />
        </Button>
        <span className="text-xs text-ink-muted">
          {error ? <span className="text-critical">{error}</span> : t("addHint")}
        </span>
      </CardBody>
    </Card>
  );
}
