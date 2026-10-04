"""JobPilot CLI. Zero extra deps (argparse). Subcommands grow per phase.

python -m jobpilot.cli config    # validate + print resolved config (Phase 0)
python -m jobpilot.cli crawl     # Phase 3
python -m jobpilot.cli serve     # Phase 2+ (API)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from jobpilot import __version__
# The task list, not the module: `build_parser` needs it to spell `--task`, and
# it has to be a real value at parser-construction time. `jobpilot.llm` itself
# imports nothing but `typing`, so this stays as cheap as the lazy imports the
# rest of this file uses for anything that touches a database or an SDK.
from jobpilot.llm import TASKS as LLM_TASKS
from jobpilot.config import CONFIG_PATH, get_config, get_secrets


def _redact(value: str) -> str:
    if not value:
        return "(empty)"
    return f"set ({len(value)} chars)"


def _redact_url(url: str) -> str:
    """Mask credentials in a connection URL (never print user/password)."""
    if not url:
        return "(empty)"
    try:
        parts = urlsplit(url)
        if parts.username or parts.password:
            host = parts.hostname or ""
            if parts.port:
                host = f"{host}:{parts.port}"
            parts = parts._replace(netloc=f"***:***@{host}")
        return urlunsplit(parts)
    except Exception:
        return "(set, redacted)"


def cmd_backfill(args: argparse.Namespace) -> int:
    """Attach quality signals and analytics facets to jobs crawled earlier.

    Idempotent: rows that already carry them are skipped, so running it twice
    costs one query and changes nothing. ``--force`` recomputes anyway, which is
    what a *parser* fix needs — otherwise the old wrong answer stays on file.
    """
    from jobpilot.companies.service import link_all_jobs
    from jobpilot.crawler.normalize import backfill_facets
    from jobpilot.crawler.quality import backfill
    from jobpilot.store.db import session_scope

    with session_scope() as db:
        touched = backfill(db, get_config())
        facets = backfill_facets(db, force=args.force)
        # Unconditional, not gated on --force: it is idempotent by construction
        # (a job already pointing at the right company is skipped) and it is the
        # repair path for a job whose employer row went missing or whose fold
        # changed. Nothing here is ever cleared, so a re-run cannot subtract.
        links = link_all_jobs(db)
    print(f"annotated {touched} job(s) with quality signals")
    print(f"derived salary/skills/city on {facets} job(s)")
    print(
        f"companies: created {links.created}, linked {links.linked} job(s)"
        + (f", {links.unlinkable} without a company name" if links.unlinkable else "")
    )
    return 0


def cmd_config(_: argparse.Namespace) -> int:
    cfg = get_config()
    sec = get_secrets()
    print(f"JobPilot v{__version__}")
    print(f"config file: {CONFIG_PATH}")
    print("\n[config.yaml]")
    print(json.dumps(cfg.model_dump(), indent=2, ensure_ascii=False))
    enabled = ", ".join(s.key for s in cfg.enabled_sources()) or "(none)"
    print(f"\nenabled sources: {enabled}")
    print("\n[secrets] (redacted)")
    print(f"  database_url        : {_redact_url(sec.database_url)}")
    # One line per model provider: which one is needed follows from `llm` above,
    # and "which key am I missing" is the question this command exists to answer.
    print(f"  anthropic_api_key   : {_redact(sec.anthropic_api_key)}")
    print(f"  openai_api_key      : {_redact(sec.openai_api_key)}")
    print(f"  google_api_key      : {_redact(sec.google_api_key)}")
    print(f"  jobpilot_api_token  : {_redact(sec.jobpilot_api_token)}")
    print(f"  slack_bot_token     : {_redact(sec.slack_bot_token)}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from jobpilot.config import REPO_ROOT
    from jobpilot.tailor.build import BuildError, build_cv, page_summary

    work_dir = args.dir or str(REPO_ROOT)
    try:
        result = build_cv(work_dir, entry=args.entry)
    except BuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1
    # Naming the engine is not cosmetic: the two are interchangeable enough that
    # you cannot tell from the PDF which one ran, and ats.py's `ligatures` finding
    # differs between them on the `plain` template.
    print(f"Built {result.pdf}  [{page_summary(result.pages)}]  via {result.engine}")
    return 0


def cmd_cv(args: argparse.Namespace) -> int:
    """CV Studio from the terminal: seed / render / build / list versions."""
    from jobpilot.cv import store
    from jobpilot.cv.compile import build_dir, compile_document
    from jobpilot.cv.render import write_document
    from jobpilot.store.db import session_scope
    from jobpilot.tailor.build import BuildError, page_summary

    with session_scope() as db:
        if args.cv_command == "seed":
            row = store.ensure_master(db)
            print(f"Master CV at version {row.version} (author={row.author})")
            return 0

        if args.cv_command == "import":
            # The only way personal data enters the app. After this it lives in
            # the database and is read through the API.
            try:
                doc = store.read_document(Path(args.file))
            except (OSError, ValueError) as exc:
                print(f"ERROR: could not read {args.file}: {exc}", file=sys.stderr)
                return 1
            row = store.save_version(db, args.scope, doc, author="user")
            name = f"{doc.header.first_name} {doc.header.last_name}".strip() or "(no name)"
            print(f"Imported into {args.scope} as v{row.version}: {name}")
            return 0

        if args.cv_command == "export":
            try:
                store.export_document(db, args.file, args.scope)
            except store.ScopeNotFound as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            print(f"Exported {args.scope} to {args.file}")
            return 0

        if args.cv_command == "versions":
            rows = store.list_versions(db, args.scope)
            if not rows:
                print(f"No versions for scope {args.scope!r}.")
                return 1
            for r in rows:
                print(f"  v{r.version:<4d} {r.author:<6s} {r.created_at}")
            return 0

        try:
            doc = store.get_document(db, args.scope)
        except store.ScopeNotFound as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if args.cv_command == "render":
        dest = write_document(doc, build_dir(args.scope))
        print(f"Rendered .tex into {dest}")
        return 0

    try:
        result = compile_document(doc, args.scope)
    except BuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1
    # Naming the engine is not cosmetic: the two are interchangeable enough that
    # you cannot tell from the PDF which one ran, and ats.py's `ligatures` finding
    # differs between them on the `plain` template.
    print(f"Built {result.pdf}  [{page_summary(result.pages)}]  via {result.engine}")
    return 0


def cmd_crawl(args: argparse.Namespace) -> int:
    from jobpilot.crawler.pipeline import default_query, run_crawl
    from jobpilot.crawler.registry import build_scrapers
    from jobpilot.store.db import session_scope

    cfg = get_config()
    scrapers = build_scrapers(cfg, respect_robots=not args.no_robots)
    if not scrapers:
        print("No enabled sources with a registered scraper. Check config.yaml.", file=sys.stderr)
        return 1

    query = args.query or default_query(cfg)
    from jobpilot.crawler.pipeline import MAX_QUERIES, split_queries

    if len(split_queries(query)) > MAX_QUERIES:
        print(f"At most {MAX_QUERIES} keywords per crawl.", file=sys.stderr)
        return 2
    limit = args.limit or cfg.crawl.jobs_per_site
    print(f"Crawling {[s.source for s in scrapers]}  query={query!r}  limit={limit}")
    with session_scope() as db:
        report = run_crawl(scrapers, cfg, db, query=query, limit=args.limit)

    for site in report.sites:
        s = site.stats
        # PART, not ok: rows the database refused are lost postings, and a
        # keyword that failed is a search that never happened — neither may
        # print like a quiet day.
        status = "FAIL" if not site.ok else ("PART" if s.rejected or site.error else "ok ")
        detail = (
            f"error={site.error}"
            if not site.ok
            else (
                f"fetched={s.fetched} new={s.inserted} upd={s.updated} "
                f"dup={s.duplicates} kept-for-jd={s.superseded} "
                f"filtered={s.filtered} fresh={s.fresh}"
                + (f" REJECTED={s.rejected} (see log: persist_failed)" if s.rejected else "")
                + (f" FAILED: {site.error}" if site.error else "")
            )
        )
        print(f"  [{status}] {site.source:14s} {detail}")
    if len(report.queries) > 1:
        for q, st in report.by_query.items():
            print(
                f"  · {q!r}: new={st.inserted} updated={st.updated}"
                + (f" FAILED on {st.errors} site(s)" if st.errors else "")
            )
    t = report.totals
    print(
        f"Total: new={t.inserted} updated={t.updated} duplicates={t.duplicates} fresh={t.fresh}"
        + (f" rejected={t.rejected}" if t.rejected else "")
        + f" (run #{report.run_id})"
    )
    return 0


def cmd_tailor(args: argparse.Namespace) -> int:
    """Tailor the Master CV to one job and report the plan (Phase 5)."""
    from jobpilot.store.db import session_scope
    from jobpilot.tailor import service
    from jobpilot.tailor.build import BuildError
    from jobpilot.tailor.engine import TailorError, default_engine
    from jobpilot.tailor.guard import GuardrailViolation

    with session_scope() as db:
        try:
            outcome = service.tailor_job(
                db,
                args.job_id,
                default_engine(),
                instruction=args.instruction,
                compile_pdf=not args.no_build,
            )
        except service.TailorRefused as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except GuardrailViolation as exc:
            print(f"GUARDRAIL: {exc}", file=sys.stderr)
            return 1
        except (TailorError, BuildError) as exc:
            print(f"FAILED: {exc}", file=sys.stderr)
            return 1

        plan = outcome.plan
        pages = "n/a" if outcome.pages is None else f"{outcome.pages} page(s)"
        print(f"{args.job_id}: v{outcome.version}  match={plan.match_score:.0%}  {pages}")
        for change in plan.changes:
            print(f"  ~ [{change.section}] {change.what}  ({change.reason})")
        for gap in plan.gaps():
            print(f"  ! gap ({gap.kind}): {gap.text}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """Dispatch an approved job to its channel (Phase 6)."""
    from jobpilot.apply import dispatcher
    from jobpilot.apply.letter import default_letter_engine
    from jobpilot.apply.portal import prefill_with_browser
    from jobpilot.store.db import session_scope

    from jobpilot import llm

    cfg = get_config()
    engine = None
    if not args.no_letter and not llm.blocker("letter"):
        engine = default_letter_engine()

    with session_scope() as db:
        try:
            outcome = dispatcher.apply_job(db, args.job_id, engine)
        except dispatcher.ApplyRefused as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1

    print(f"{args.job_id}: channel={outcome.channel} result={outcome.result}")
    print(f"  {outcome.detail}")
    if outcome.result == "dry_run":
        gates = cfg.apply.email
        print(
            f"  gates: enabled={gates.enabled} dry_run={gates.dry_run} "
            f"test_recipient={gates.test_recipient or '(none)'}"
        )
    if outcome.handoff:
        print(f"  open: {outcome.handoff.url}")
        print(f"  CV  : {outcome.handoff.cv_path}")
        for key, value in outcome.handoff.fields.items():
            print(f"    {key:<12} {value}")
        if args.open_portal:
            prefill_with_browser(outcome.handoff)
        print("  when you've submitted it, run: jobpilot confirm-submit " + args.job_id)
    return 0 if outcome.result != "failed" else 1


def cmd_confirm_submit(args: argparse.Namespace) -> int:
    from jobpilot.apply import dispatcher
    from jobpilot.store.db import session_scope

    with session_scope() as db:
        try:
            job = dispatcher.confirm_submit(db, args.job_id)
        except dispatcher.ApplyRefused as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        print(f"{args.job_id}: {job.status.value}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Crawl, report, and stop — optionally on a loop (PLAN.md §9 'cron nhẹ').

    A plain loop rather than a scheduler dependency: it is one less thing to
    install, and `--every` is easy to reason about when it wakes at 3am.
    """
    import time

    from jobpilot.orchestrator import crawl_body

    def once() -> int:
        try:
            result = crawl_body(query=args.query, respect_robots=not args.no_robots)(print)
        except Exception as exc:
            print(f"CRAWL FAILED: {exc}", file=sys.stderr)
            return 1
        for site in result["sites"]:
            rejected = site.get("rejected", 0)
            partial = site["ok"] and site.get("error")
            status = "FAIL" if not site["ok"] else ("PART" if rejected or partial else "ok ")
            detail = (
                f"error={site['error']}"
                if not site["ok"]
                else (
                    f"fetched={site['fetched']} new={site['inserted']} "
                    f"upd={site['updated']} dup={site['duplicates']} "
                    f"kept-for-jd={site.get('superseded', 0)} fresh={site['fresh']}"
                    + (f" REJECTED={rejected} (see log: persist_failed)" if rejected else "")
                    + (f" FAILED: {site['error']}" if partial else "")
                )
            )
            print(f"  [{status}] {site['source']:14s} {detail}")
        t = result["totals"]
        print(f"Total: new={t['inserted']} updated={t['updated']} fresh={t['fresh']}")
        # Individual site failures are normal and don't fail the batch, but a run
        # where nothing worked should be visible to whatever scheduled it.
        sites = result["sites"]
        return 1 if sites and not any(s["ok"] for s in sites) else 0

    if not args.every:
        return once()

    print(f"Looping every {args.every} minutes — Ctrl-C to stop.")
    try:
        while True:
            once()
            print(f"-- sleeping {args.every}m --")
            time.sleep(args.every * 60)
    except KeyboardInterrupt:
        print("\nstopped")
        return 0


def cmd_slack(args: argparse.Namespace) -> int:
    """Run the Slack companion app (Phase 7). Needs the API already running."""
    from jobpilot.slack.app import SlackNotConfigured, run

    try:
        run(api_base=args.api, web_base=args.web)
    except SlackNotConfigured as exc:
        print(f"Slack not started: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


def cmd_llm(args: argparse.Namespace) -> int:
    """Compare model backends on evidence rather than on vibes (Phase 20b)."""
    from jobpilot import llm

    if args.llm_command == "stats":
        return _llm_stats(args)
    if args.llm_command == "providers":
        from jobpilot.llm.pricing import CHECKED_ON, policy_for
        from jobpilot.llm.redact import shadowed_secrets
        from jobpilot.llm.registry import PROVIDERS, api_key, ready

        cfg = get_config().llm
        for name, provider in sorted(PROVIDERS.items()):
            note = policy_for(name, paid_tier=cfg.paid_tier(name))
            if note and note.trains_on_input:
                trains = "MAY TRAIN (account setting)" if note.depends_on_account else "TRAINS ON INPUT"
            else:
                trains = "no training"
            if api_key(name):
                key = "key set"
            elif provider.key_optional:
                key = "uses claude login" if ready(name) else "not usable (see below)"
            else:
                key = f"no {provider.env_var}"
            print(f"{name:10} {provider.default_model:24} {key:30} {trains}")

        # "key set" above is not the same as "the key you edited is the one in
        # use". An environment variable beats .env and says nothing about it.
        for name in shadowed_secrets():
            print(
                f"\n!! {name} exists BOTH as an environment variable and in .env, "
                f"with different values.\n"
                f"   The environment variable wins, so your .env edit is being ignored.\n"
                f'   Fix on Windows: setx {name} "" then open a NEW terminal.'
            )
        print(f"\nData-use notes checked {CHECKED_ON}. Currently configured:")
        for task in llm.TASKS:
            blocked = llm.blocker(task)
            suffix = f"  [BLOCKED: {blocked}]" if blocked else ""
            print(f"  {task:9} {cfg.for_task(task):8} {cfg.model_for(task)}{suffix}")
            for line in llm.warnings(task):
                print(f"      ! {line}")
        return 0

    # bench
    # An explicit --provider is its own answer to "which backend"; only check
    # the configured one when the caller did not name one.
    if not args.provider:
        blocked = llm.blocker(args.task)
        if blocked:
            print(f"cannot bench: {blocked}", file=sys.stderr)
            return 1
        for line in llm.warnings(args.task):
            print(f"! {line}", file=sys.stderr)

    from jobpilot.llm.bench import bench_classify, bench_intake, bench_tailor
    from jobpilot.store.db import session_scope

    if args.task == "classify":
        result = bench_classify(limit=args.limit, provider=args.provider, model=args.model)
    elif args.task == "intake":
        result = bench_intake(limit=args.limit, provider=args.provider, model=args.model)
    else:
        with session_scope() as db:
            result = bench_tailor(
                db, limit=args.limit or 4, provider=args.provider, model=args.model
            )

    print(f"{result.task} on {result.provider} / {result.model}")
    if result.task == "classify":
        print(f"  {result.correct}/{result.total} labels correct")
    elif result.task == "intake":
        # Fields, not postings — a model that reads the salary right and invents
        # a seniority has got one of two things right, not one of one.
        print(f"  {result.correct}/{result.total} fields correct")
    else:
        print(f"  {result.correct}/{result.total} plans cleared the guardrails")
        print(f"  {result.first_try}/{result.total} on the first round (no corrective retry)")
    if result.failed:
        print(f"  {result.failed} call(s) failed outright")
    for note in result.notes:
        print(f"  - {note}")
    # What it cost is in llm_calls, where every other run's cost also is.
    print("\ncost and latency: python -m jobpilot.cli llm stats")
    return 0 if result.total and not result.failed else 1


def _llm_stats(args: argparse.Namespace) -> int:
    from jobpilot.llm.stats import MIN_SAMPLE, backend_stats
    from jobpilot.store.db import session_scope

    with session_scope() as db:
        rows = backend_stats(db, task=args.task)

    if not rows:
        print("no model calls recorded yet")
        return 0

    header = f"{'task':9} {'provider':8} {'model':24} {'n':>4} {'cost':>9} {'1st try':>8} {'ok':>6} {'p50':>7} {'p95':>7}"
    print(header)
    print("-" * len(header))
    for row in rows:
        cost = "-" if row["cost_usd"] is None else f"${row['cost_usd']:.4f}"
        # A rate withheld for a small sample must not look like a missing value:
        # print the count that is the honest answer instead.
        first = _rate(row["first_try_rate"], row["attempts"])
        okay = _rate(row["success_rate"], row["attempts"])
        print(
            f"{row['task']:9} {row['provider']:8} {row['model']:24} {row['attempts']:>4} "
            f"{cost:>9} {first:>8} {okay:>6} {row['p50_latency_ms']:>6}ms {row['p95_latency_ms']:>6}ms"
        )
        if row["unpriced_rounds"]:
            print(f"{'':9} {'':8} `- {row['unpriced_rounds']} round(s) had no price in pricing.py")
    print(f"\nrates shown from {MIN_SAMPLE} attempts up; below that, 'n=<count>' is the answer")
    return 0


def _rate(value: float | None, attempts: int) -> str:
    return f"n={attempts}" if value is None else f"{value:.0%}"


def cmd_backup(args: argparse.Namespace) -> int:
    """Dump the database and export the CV. Same code the dashboard button runs."""
    from jobpilot.backup import BackupError, list_backups, restore_hint, run_backup

    if args.list:
        files = list_backups(args.dir)
        if not files:
            print("no backups yet")
            return 0
        for f in files:
            # .astimezone() because the timestamp is stored UTC but the name is
            # stamped in local time; printing the two side by side unconverted
            # shows one instant as two different clock readings on one line.
            when = f.created.astimezone()
            print(f"{when:%Y-%m-%d %H:%M}  {f.size/1024:8.1f} KB  {f.name}")
        hint = restore_hint(args.dir)
        if hint:
            print(f"\nrestore the newest with:\n  {hint}")
        return 0

    # backup_body, not run_backup: it is the one that also writes the Run row.
    # The scheduled task runs this command, so calling run_backup here left the
    # dashboard's "Recent runs" empty after every nightly backup — while the
    # page told the reader that an empty list means the job never fired. A
    # monitoring feature reporting the exact opposite of the truth is worse than
    # not having one.
    #
    # --dir is honoured by running the plain function, which skips the Run row;
    # that is for ad-hoc dumps to a scratch directory, not for the schedule.
    from jobpilot.backup import backup_body

    step = (lambda m: print(f"  {m}...")) if args.verbose else None
    try:
        if args.dir:
            r = run_backup(args.dir, progress=step)
            result = {"dump": r.dump.name, "cv": r.cv.name, "size": r.size,
                      "mirrored_to": r.mirrored_to, "pruned": len(r.pruned), "notes": r.notes}
        else:
            result = backup_body(step or (lambda _m: None))
    except BackupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"{result['dump']} + {result['cv']}  ({result['size']/1024:.1f} KB)")
    if result["mirrored_to"]:
        print(f"mirrored to {result['mirrored_to']}")
    for note in result.get("notes", []):
        print(f"NOTE: {note}")
    if result["pruned"]:
        print(f"pruned {result['pruned']} file(s) past the retention window")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed — run: pip install -e '.[api]'", file=sys.stderr)
        return 1

    if args.workers != 1:
        # Not a preference. The task queue is a ThreadPoolExecutor living inside
        # this process (orchestrator.py, bound in the API's lifespan), so a
        # second uvicorn worker is a second, independent queue with its own
        # WebSocket manager. The "one task per job" guard in queue.submit() only
        # sees its own process, so the same job gets tailored twice at once;
        # progress for a task started in worker A never reaches a dashboard
        # connected to worker B. Both failures are silent — hence a hard refusal
        # rather than a warning nobody reads in a service log.
        print(
            f"--workers {args.workers} is not supported: the task queue is in-process, "
            "so extra workers each get their own queue and the one-task-per-job "
            "guard stops holding. Run one worker.",
            file=sys.stderr,
        )
        return 2

    uvicorn.run(
        "jobpilot.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=1,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobpilot", description="JobPilot CLI")
    parser.add_argument("--version", action="version", version=f"jobpilot {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("config", help="validate & print resolved config").set_defaults(func=cmd_config)
    p_backfill = sub.add_parser(
        "backfill", help="add quality signals + analytics facets to older jobs"
    )
    # A parser fix has to be re-runnable over rows that already hold its old,
    # wrong answer — otherwise the bug is frozen into the data it corrupted.
    p_backfill.add_argument(
        "--force", action="store_true", help="recompute facets even if already present"
    )
    p_backfill.set_defaults(func=cmd_backfill)

    p_build = sub.add_parser(
        "build", help="compile a CV to PDF with tectonic"
    )
    p_build.add_argument("dir", nargs="?", default=None, help="work dir (default: repo root)")
    p_build.add_argument("--entry", default="cv.tex", help="LaTeX entry file")
    p_build.set_defaults(func=cmd_build)
    p_cv = sub.add_parser("cv", help="CV Studio: seed/import/export/render/build (Phase 4.5)")
    cv_sub = p_cv.add_subparsers(dest="cv_command", required=True)
    cv_sub.add_parser("seed", help="create an empty Master CV if there isn't one (idempotent)")

    p_import = cv_sub.add_parser("import", help="load a CV JSON file into the database")
    p_import.add_argument("file", help="path to a CV document JSON")
    p_import.add_argument("--scope", default="master", help="'master' or a job id")

    p_export = cv_sub.add_parser("export", help="write a CV from the database to JSON (backup)")
    p_export.add_argument("file", help="destination path — use *.local.json to stay gitignored")
    p_export.add_argument("--scope", default="master", help="'master' or a job id")
    for name, helptext in (
        ("render", "write the structured CV out as .tex"),
        ("build", "render + compile to PDF (see cv.engine)"),
        ("versions", "list the version history"),
    ):
        sp = cv_sub.add_parser(name, help=helptext)
        sp.add_argument("scope", nargs="?", default="master", help="'master' or a job id")
    p_cv.set_defaults(func=cmd_cv)

    p_crawl = sub.add_parser("crawl", help="crawl enabled sources into the DB (Phase 3)")
    p_crawl.add_argument("--query", default=None, help="keywords, comma-separated: each is its own search (default: crawl.queries)")
    p_crawl.add_argument(
        "--no-robots", action="store_true", help="skip robots.txt checks (debug only)"
    )
    p_crawl.add_argument(
        "--limit",
        type=int,
        default=None,
        help="jobs per site for this run (default: config crawl.jobs_per_site)",
    )
    p_crawl.set_defaults(func=cmd_crawl)
    p_tailor = sub.add_parser("tailor", help="tailor the Master CV to a job (Phase 5)")
    p_tailor.add_argument("job_id", help="job id, e.g. itviec:2156537")
    p_tailor.add_argument(
        "--instruction", default=None, help="revision instruction for an edit round"
    )
    p_tailor.add_argument(
        "--no-build", action="store_true", help="produce the plan without building the PDF"
    )
    p_tailor.set_defaults(func=cmd_tailor)

    p_apply = sub.add_parser("apply", help="dispatch an approved job to its channel (Phase 6)")
    p_apply.add_argument("job_id")
    p_apply.add_argument("--no-letter", action="store_true", help="skip the cover letter")
    p_apply.add_argument(
        "--open-portal",
        action="store_true",
        help="for portal jobs, open a visible browser and pre-fill what it can (never submits)",
    )
    p_apply.set_defaults(func=cmd_apply)

    p_confirm = sub.add_parser("confirm-submit", help="mark a portal/external job as submitted")
    p_confirm.add_argument("job_id")
    p_confirm.set_defaults(func=cmd_confirm_submit)

    p_llm = sub.add_parser("llm", help="compare model backends: providers/stats/bench (Phase 20b)")
    llm_sub = p_llm.add_subparsers(dest="llm_command", required=True)
    llm_sub.add_parser("providers", help="what is configured, what it costs you in privacy")
    p_llm_stats = llm_sub.add_parser("stats", help="cost, first-try rate and latency per backend")
    p_llm_stats.add_argument("--task", choices=LLM_TASKS, default=None)
    p_llm_bench = llm_sub.add_parser("bench", help="score the configured backend on known answers")
    p_llm_bench.add_argument("--task", choices=("intake", "tailor", "classify"), default="classify")
    p_llm_bench.add_argument(
        "--limit", type=int, default=0, help="how many cases (tailor: real jobs from the DB)"
    )
    # Sweeping candidate models should be a loop, not a series of config edits.
    p_llm_bench.add_argument("--provider", default="", help="override the configured provider")
    p_llm_bench.add_argument("--model", default="", help="override the model id")
    p_llm.set_defaults(func=cmd_llm)

    p_backup = sub.add_parser("backup", help="pg_dump + CV export, with retention")
    p_backup.add_argument("--dir", default=None, help="destination (default: backup.dir in config)")
    p_backup.add_argument("--list", action="store_true", help="show existing backups instead")
    p_backup.add_argument("-v", "--verbose", action="store_true", help="print each step")
    p_backup.set_defaults(func=cmd_backup)

    p_serve = sub.add_parser("serve", help="run FastAPI backend (Phase 2)")
    p_serve.add_argument("--host", default="127.0.0.1", help="bind host (localhost only)")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true", help="auto-reload on code change")
    p_serve.add_argument(
        "--workers",
        type=int,
        default=1,
        help="must be 1 — the task queue is in-process (see cmd_serve)",
    )
    p_serve.set_defaults(func=cmd_serve)
    p_slack = sub.add_parser("slack", help="run the Slack companion app (Phase 7)")
    p_slack.add_argument(
        "--api",
        default="http://127.0.0.1:8000/api",
        help="JobPilot API base URL (must include the /api prefix)",
    )
    p_slack.add_argument("--web", default="http://localhost:5173", help="dashboard base URL")
    p_slack.set_defaults(func=cmd_slack)

    p_run = sub.add_parser("run", help="crawl once, or on a loop (Phase 8)")
    p_run.add_argument("--query", default=None, help="keywords, comma-separated: each is its own search (default: crawl.queries)")
    p_run.add_argument("--no-robots", action="store_true", help="skip robots.txt (debug only)")
    p_run.add_argument("--every", type=int, default=0, help="repeat every N minutes")
    p_run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
