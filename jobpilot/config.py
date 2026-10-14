"""Config loading for JobPilot.

Two layers:
  * config.yaml  -> non-secret settings (crawl rules, sources, apply, cv)  -> `Config`
  * .env         -> secrets (DB url, API keys, tokens)                     -> `Secrets`

Usage:
    from jobpilot.config import get_config, get_secrets
    cfg = get_config()
    sec = get_secrets()
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, get_args, get_origin

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
CONFIG_PATH = PACKAGE_DIR / "config.yaml"
# Overlay written by the Settings page. config.yaml is heavily commented and
# those comments are load-bearing documentation (the email safety gates most of
# all), and YAML round-tripping would strip them — so edits land in a separate,
# gitignored file that is merged on top instead.
LOCAL_CONFIG_PATH = PACKAGE_DIR / "config.local.yaml"


# --------------------------------------------------------------------------- #
# Non-secret config (config.yaml)
# --------------------------------------------------------------------------- #
class AppCfg(BaseModel):
    timezone: str = "Asia/Ho_Chi_Minh"
    edit_max_rounds: int = 3
    #: Most projects a tailored CV shows. The Master keeps them all (it is the
    #: store); a tailored CV keeps the ones that fit the job. 0 = no limit.
    tailor_max_projects: int = 3


class CrawlCfg(BaseModel):
    jobs_per_site: int = 10
    # Listing pages to walk per site before giving up on reaching jobs_per_site.
    # A ceiling, not a target: a board with 50 cards a page never leaves page 1.
    max_pages: int = 5
    fresh_hours: int = 48
    # A posting older than this is flagged (never hidden) as possibly filled.
    stale_days: int = 45
    # How long one board's copy of a role keeps another board's copy out,
    # counted from the last time the role was seen (not the first). 0 turns
    # cross-source dedup off entirely, which is the honest way to say "show me
    # every board's version" — see crawler/persist.py.
    dedup_days: int = 14
    rate_limit_seconds: tuple[float, float] = (2.0, 5.0)
    match_score_min: float = 0.30
    stacks: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    #: What the scheduled crawl (and an empty search box) searches for — one
    #: search per entry, each run on every site. Empty = the old single query
    #: joined from the first three ``stacks``, which is long enough that some
    #: boards (TopCV puts it in the URL path) answer it with nothing.
    queries: list[str] = Field(default_factory=list)

    #: One Vietnamese city to hold ITviec, TopCV and VietnamWorks to — "Ho Chi
    #: Minh", "hcm", "Hà Nội". Empty = every city. Company boards have their
    #: own scope (``ats.locations``); remote feeds have none.
    city: str = ""
    #: Where you want to work — "Ho Chi Minh", "Ha Noi", "Vietnam", "Remote", or
    #: a place abroad. Narrows the search where a source can be narrowed and
    #: then keeps only postings that are there (or say nothing about where).
    #: Empty = anywhere, and `city` / `ats.locations` apply as before.
    places: list[str] = Field(default_factory=list)
    #: onsite / hybrid / remote. Empty = any. A posting that does not state its
    #: work mode is always kept (crawler/scope.py).
    work_modes: list[str] = Field(default_factory=list)

    @field_validator("work_modes")
    @classmethod
    def _known_modes(cls, value: list[str]) -> list[str]:
        from jobpilot.crawler.normalize import WORK_MODES

        bad = [m for m in value if m not in WORK_MODES]
        if bad:
            raise ValueError(f"crawl.work_modes: {bad} — use {list(WORK_MODES)}")
        return value

    @field_validator("city")
    @classmethod
    def _known_city(cls, value: str) -> str:
        """Refused at save time. A city the crawler cannot read would otherwise
        be dropped with a log line at 08:30, and the crawl would go on
        nationwide under a setting that says it does not."""
        value = (value or "").strip()
        if not value:
            return ""
        from jobpilot.crawler.vietnam import scope_city

        if scope_city(value) is None:
            raise ValueError(
                f"crawl.city {value!r} is not a Vietnamese city the crawler knows — "
                'write one city, e.g. "Ho Chi Minh", "Ha Noi" or "Da Nang"'
            )
        return value

    @field_validator("queries")
    @classmethod
    def _bounded_queries(cls, value: list[str]) -> list[str]:
        """Refused at save time, not at 08:30. Without this, nine keywords saved
        from Settings made every scheduled `cli crawl` exit on the 8-keyword
        limit, with the reason visible only in a log nobody reads."""
        if not value:
            return value
        from jobpilot.crawler.pipeline import MAX_QUERIES, split_queries

        if len(split_queries(", ".join(value))) > MAX_QUERIES:
            raise ValueError(
                f"at most {MAX_QUERIES} scheduled keywords — each is a full pass over every site"
            )
        return value


class SourceCfg(BaseModel):
    key: str
    tier: int = 1
    enabled: bool = False


class AtsCfg(BaseModel):
    """Company boards to read per ATS platform (PLAN §5.1.1 tier 3).

    A token is the company's slug in its careers-page URL — the ``gitlab`` in
    ``job-boards.greenhouse.io/gitlab``. Adding a company is one word here;
    there is no per-company code.
    """

    greenhouse: list[str] = Field(default_factory=list)
    lever: list[str] = Field(default_factory=list)
    #: Full URL of a careers site's Indeed-style XML feed.
    careerfeed: list[str] = Field(default_factory=list)
    #: ``<tenant>.wdN.myworkdayjobs.com/<site>``.
    workday: list[str] = Field(default_factory=list)
    #: ``<careers host>/<company domain>``.
    eightfold: list[str] = Field(default_factory=list)
    #: ``google`` to read Google's own careers site (it has one board).
    googlecareers: list[str] = Field(default_factory=list)
    #: Keep only postings in these places ("Ho Chi Minh", "Vietnam"). Matched
    #: against the posting's own location label. Vietnamese cities are known by
    #: their spellings ("HCMC", "Saigon") and "Vietnam" by its cities; any other
    #: term has to be something the board actually writes. Empty = every location — and a company board
    #: is worldwide, so then the per-site limit goes to whichever offices are
    #: listed first, and the stack gate stays on.
    locations: list[str] = Field(default_factory=list)

    def boards_for(self, key: str) -> list[str]:
        return list(getattr(self, key, []) or [])


class EmailCfg(BaseModel):
    """Email is the one channel allowed to send without a second confirmation
    (CLAUDE.md rule 2), so it is gated three ways: off by default, dry-run by
    default, and able to redirect every message to your own inbox until you
    trust it."""

    enabled: bool = False
    method: Literal["gmail", "smtp"] = "gmail"
    from_addr: str = ""
    from_name: str = ""
    # Build and record the message, but never hand it to a mail server.
    dry_run: bool = True
    # Deliver to this address instead of the employer — "test email mình trước"
    # (PLAN.md §9 Phase 6). Empty means mail really goes to the job's contact.
    test_recipient: str = ""
    subject_template: str = "Application for {title} — {name}"


class LlmCfg(BaseModel):
    """Which model runs which job.

    Deliberately **per task**, because the three calls are not equally hard.
    Classifying an email into one of six labels and copying one sentence out of
    it is nothing like writing 300 words a stranger will judge you on. The
    tailor sits between them, and its schema does most of the work: the plan is
    index-based, so the model reorders numbered items rather than writing a CV.

    Default stays ``claude`` — switching a user's model silently would change
    what their applications say.

    ``provider`` is a plain string validated against the registry rather than a
    ``Literal``. A ``Literal`` has to be edited in four places to admit a fourth
    backend, and the point of the registry is that it doesn't.
    """

    provider: str = "claude"

    # "" means "use `provider`". Set one to mix — the four calls differ enough
    # in difficulty that one backend for all of them is a coincidence, not a
    # design.
    tailor: str = ""
    letter: str = ""
    classify: str = ""
    intake: str = ""

    #: provider key -> model id. Anything absent falls back to that provider's
    #: own default, so a user switching backend does not have to know model ids.
    models: dict[str, str] = Field(default_factory=dict)

    #: task -> model id, overriding ``models`` for that one call. This is where
    #: "classify does not need the expensive model" gets said out loud.
    task_models: dict[str, str] = Field(default_factory=dict)

    #: Gemini is the one provider whose data-use terms differ by tier, and the
    #: tier cannot be read off an API key. Ask once, record it, warn accordingly.
    gemini_paid_tier: bool = True

    #: provider -> dollars you have put on that account. Entered by hand because
    #: it cannot be fetched: every provider's spend endpoint needs an *Admin* key,
    #: not the ordinary one JobPilot holds (verified — all three answer 401).
    #: "Remaining" is therefore this number minus what JobPilot itself recorded
    #: spending, which does not know about usage from anywhere else. It is a
    #: budget tracker, not a balance, and the UI has to say so.
    budget_usd: dict[str, float] = Field(default_factory=dict)

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        from jobpilot.llm.registry import PROVIDERS

        if value not in PROVIDERS:
            raise ValueError(f"unknown provider {value!r} — known: {', '.join(sorted(PROVIDERS))}")
        return value

    @field_validator("tailor", "letter", "classify", "intake")
    @classmethod
    def _known_override(cls, value: str) -> str:
        from jobpilot.llm.registry import PROVIDERS

        if value and value not in PROVIDERS:
            raise ValueError(f"unknown provider {value!r} — known: {', '.join(sorted(PROVIDERS))}")
        return value

    def for_task(self, task: Literal["tailor", "letter", "classify", "intake"]) -> str:
        """The provider that should run ``task``."""
        return getattr(self, task) or self.provider

    def model_for(self, task: Literal["tailor", "letter", "classify", "intake"]) -> str:
        """The model id for ``task``: task override, then provider default."""
        from jobpilot.llm.registry import PROVIDERS

        provider = self.for_task(task)
        return (
            self.task_models.get(task)
            or self.models.get(provider)
            or PROVIDERS[provider].default_model
        )

    def paid_tier(self, provider: str) -> bool:
        """Whether ``provider`` is being used on a paid plan.

        Only Gemini distinguishes; everyone else is answered ``True`` because
        their API terms do not change with the plan.
        """
        return self.gemini_paid_tier if provider == "gemini" else True


class InboxCfg(BaseModel):
    """Reading employer replies out of your own mailbox (Phase 19).

    Off by default. Reading somebody's mail is not a thing to switch on for
    them, even when the reading is local and read-only.

    ``folder`` is the escape hatch for anyone who would rather not point this at
    a whole inbox: file replies into a label with a mail rule and name it here,
    and nothing outside it is ever opened. The default is still INBOX, because a
    reply you forgot to file is a reply JobPilot would never see.
    """

    enabled: bool = False
    folder: str = "INBOX"
    since_days: int = 30
    # Messages read per pass, newest first. Matching is local, so this bounds
    # mail *read*, not mail sent anywhere.
    limit: int = 100


class ApplyCfg(BaseModel):
    email: EmailCfg = Field(default_factory=EmailCfg)
    portal_prefill: bool = True
    inbox: InboxCfg = Field(default_factory=InboxCfg)

    def email_blocker(self) -> str:
        """Why the email channel may not run, or '' if it may."""
        if not self.email.enabled:
            return "email apply is disabled (apply.email.enabled)"
        if not self.email.from_addr:
            return "apply.email.from_addr is not set"
        return ""

    def inbox_blocker(self, secrets: "Secrets | None" = None) -> str:
        """Why the inbox sync may not run, or '' if it may."""
        if not self.inbox.enabled:
            return "inbox sync is off (apply.inbox.enabled)"
        s = secrets or get_secrets()
        if not s.imap_user or not s.imap_password:
            return (
                "IMAP_USER / IMAP_PASSWORD are not set in .env — for Gmail this must be "
                "an App Password, not your account password"
            )
        return ""


class CvCfg(BaseModel):
    master_dir: str = "resume"
    out_dir: str = "out"

    #: Which LaTeX engine builds the PDF: ``auto`` | ``tectonic`` (the same
    #: thing today). ``docker`` was removed; a config still naming it gets a
    #: build error saying so. An old ``docker_image`` key is simply ignored.
    #:
    #: Deliberately a plain str rather than a Literal: get_config() is called on
    #: nearly every request, so a Literal turns one typo in config.local.yaml
    #: into a ValidationError that takes the whole app down instead of one
    #: build. jobpilot/tailor/build.py:resolve_engine validates it at the point
    #: of use and names the valid values.
    engine: str = "auto"

    #: Command or path for the tectonic binary. A path with a directory
    #: component works too, for a binary kept off PATH.
    tectonic_bin: str = "tectonic"

    theme: str = "awesome-red"


class BackupCfg(BaseModel):
    """Where backups go and how long they live (``jobpilot/backup.py``)."""

    #: Outside the repo on purpose: it holds personal data, and a backup living
    #: inside the thing it backs up survives fewer accidents than it looks.
    dir: str = "~/JobPilotBackups"
    keep_days: int = 30

    #: Hard cap on how many backups are kept, regardless of age.
    #:
    #: Age alone is not enough: pressing the dashboard button five times in an
    #: afternoon writes ten files that are all within the age window, so nothing
    #: is ever pruned and the directory grows without bound. Whichever limit
    #: bites first wins.
    keep_last: int = 14

    #: An rclone remote, e.g. ``gdrive:JobPilotBackups``. Empty = local only.
    remote: str = ""

    #: Deliberately longer than ``keep_days``. The off-machine copy exists for
    #: the case where this machine is gone, so it must not be governed by the
    #: pruning pass that runs here — a bug in local retention would otherwise
    #: delete the surviving copies too. Different lifetimes are what make it a
    #: second copy rather than a mirror of one failure.
    remote_keep_days: int = 90


class Config(BaseModel):
    app: AppCfg = Field(default_factory=AppCfg)
    crawl: CrawlCfg = Field(default_factory=CrawlCfg)
    sources: list[SourceCfg] = Field(default_factory=list)
    ats: AtsCfg = Field(default_factory=AtsCfg)
    apply: ApplyCfg = Field(default_factory=ApplyCfg)
    cv: CvCfg = Field(default_factory=CvCfg)
    backup: BackupCfg = Field(default_factory=BackupCfg)
    llm: LlmCfg = Field(default_factory=LlmCfg)

    def enabled_sources(self) -> list[SourceCfg]:
        return [s for s in self.sources if s.enabled]


# --------------------------------------------------------------------------- #
# Secrets (.env)
# --------------------------------------------------------------------------- #
class Secrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://jobpilot:jobpilot@localhost:5432/jobpilot"
    jobpilot_api_token: str = "changeme"

    # One per model provider; which one is needed follows from `llm` in
    # config.yaml. `jobpilot.llm.blocker` names the missing one before a task is
    # queued rather than after it has been sitting in the queue.
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    #: From `claude setup-token`: the `claude_cli` provider runs on your Claude
    #: subscription with it, instead of per-token API billing.
    claude_code_oauth_token: str = ""

    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_channel_id: str = ""

    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Reading *your own* mailbox for LinkedIn Job Alerts (Phase 9). Gmail needs
    # an App Password, not your account password — see CLAUDE.md.
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""


def deep_merge(base: dict, overlay: dict) -> dict:
    """Overlay wins, but only for the keys it actually sets."""
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def merge_sources(base: list, overlay: list) -> list:
    """Merge the source list *by key* instead of replacing it wholesale.

    ``deep_merge`` overwrites lists, which is right for ``stacks`` but wrong
    here: the overlay written by the Settings page holds one entry per source
    that existed *when it was saved*, so a plain overwrite makes every source
    added to ``config.yaml`` since then vanish. Not merely default-off —
    absent, and therefore impossible to switch on in the Settings page that
    caused it. Adding the tier-2 feeds hit exactly that.

    So ``config.yaml`` owns the catalogue and its order; the overlay only
    carries your preferences for the sources it names. A key the overlay
    invents is still kept, so a hand-added source is not silently dropped.
    """
    merged = {s["key"]: dict(s) for s in base if isinstance(s, dict) and s.get("key")}
    order = list(merged)
    for src in overlay or []:
        if not isinstance(src, dict) or not src.get("key"):
            continue
        key = src["key"]
        if key in merged:
            merged[key].update(src)
        else:
            merged[key] = dict(src)
            order.append(key)
    return [merged[k] for k in order]


def resolve_config(base: dict, overlay: dict) -> dict:
    """``config.yaml`` + ``config.local.yaml`` → the settings the app runs on."""
    data = deep_merge(base, overlay)
    if isinstance(base.get("sources"), list):
        data["sources"] = merge_sources(base["sources"], overlay.get("sources") or [])
    return data


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache
def get_config(path: Path | None = None) -> Config:
    p = path or CONFIG_PATH
    return Config.model_validate(resolve_config(_read_yaml(p), _read_yaml(LOCAL_CONFIG_PATH)))


def prune_to_schema(model: type[BaseModel], data: dict) -> dict:
    """Drop keys ``model`` does not declare, recursively.

    Pydantic *ignores* unknown fields rather than rejecting them, so validation
    happily passes on a payload carrying extras — and the overlay is written
    from the raw dict, not from the validated object. A ``PUT /settings`` body
    of ``{"llm": {"anthropic_api_key": "sk-…"}}`` would therefore validate and
    then persist a live API key into ``config.local.yaml``.

    That file is gitignored, so it is not a commit risk; it is a *principle 6*
    risk — secrets live in ``.env`` and nowhere else. Pruning here rather than
    in one request schema fixes every section at once: ``app``, ``crawl``,
    ``apply`` and ``cv`` are all plain dicts on the way in and had the same hole.
    """
    out: dict = {}
    for key, value in data.items():
        field = model.model_fields.get(key)
        if field is None:
            continue
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            out[key] = prune_to_schema(annotation, value) if isinstance(value, dict) else value
            continue
        if get_origin(annotation) is list and isinstance(value, list):
            args = get_args(annotation)
            item = args[0] if args else None
            if isinstance(item, type) and issubclass(item, BaseModel):
                out[key] = [prune_to_schema(item, v) if isinstance(v, dict) else v for v in value]
                continue
        out[key] = value
    return out


#: Settings that may only be changed by editing a file on the host, never
#: through the API.
#:
#: These are the three gates standing between "JobPilot drafted an email" and
#: "JobPilot sent an email to a stranger on your behalf" (``apply/email.py``).
#: Every other setting on that page is a preference; these decide whether a
#: machine speaks in your name. An HTTP request that can flip them turns one
#: leaked token into outgoing mail, so the shortest path to sending is
#: deliberately not on the network at all — you have to be on the host.
LOCKED_SETTINGS: tuple[tuple[str, ...], ...] = (
    ("apply", "email", "enabled"),
    ("apply", "email", "dry_run"),
    ("apply", "email", "test_recipient"),
)


def _dig(data: object, path: tuple[str, ...]):
    """Value at ``path``, or ``KeyError`` if the patch doesn't set it."""
    for key in path:
        if not isinstance(data, dict) or key not in data:
            raise KeyError(path)
        data = data[key]
    return data


def locked_violations(patch: dict, current: Config | None = None) -> list[str]:
    """Which locked settings ``patch`` would actually change.

    Only *changes* are rejected, not mere presence. The Settings page saves a
    whole section at a time, so it resends these fields on every save of an
    unrelated preference; refusing those would make the page unusable and teach
    everyone to route around the lock. Sending the value it already has is a
    no-op and is allowed to pass.
    """
    cfg = current or get_config()
    out = []
    for path in LOCKED_SETTINGS:
        try:
            proposed = _dig(patch, path)
        except KeyError:
            continue
        if proposed != _dig(cfg.model_dump(), path):
            out.append(".".join(path))
    return out


def save_local_config(patch: dict) -> Config:
    """Merge ``patch`` into the overlay, validate the result, then persist it.

    Validating before writing means a bad Settings save is rejected rather than
    leaving the app unable to load its own config on next start.
    """
    # Prune before merging: what gets written is the raw dict, so anything not
    # removed here reaches disk regardless of what validation thinks.
    merged_overlay = deep_merge(_read_yaml(LOCAL_CONFIG_PATH), prune_to_schema(Config, patch))
    # Validate exactly what get_config() will build, or a save can pass here and
    # then fail on the next start.
    Config.model_validate(resolve_config(_read_yaml(CONFIG_PATH), merged_overlay))

    header = (
        "# Written by the JobPilot Settings page — merged on top of config.yaml.\n"
        "# Safe to delete: that just restores the defaults in config.yaml.\n"
    )
    LOCAL_CONFIG_PATH.write_text(
        header + yaml.safe_dump(merged_overlay, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    get_config.cache_clear()
    return get_config()


@lru_cache
def get_secrets() -> Secrets:
    return Secrets()
