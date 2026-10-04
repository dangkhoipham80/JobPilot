"""Model backends.

The pipeline calls a language model in four places — tailoring a CV, writing a
cover letter, classifying an employer's reply, and reading a job description the
user pasted in — and each of them is a
``Protocol`` with one implementation that takes a
:class:`~jobpilot.llm.base.StructuredClient`. Which company answers is a config
decision, per task, because the three are not equally demanding: classifying an
email into one of six labels is nothing like writing 300 words a stranger will
judge you on.

The split between *how you call a model* and *what makes the answer acceptable*
is the load-bearing one. Providers live here; guardrails live with the task they
guard, and every backend goes through the same ones.
"""

from __future__ import annotations

from typing import Literal

Task = Literal["tailor", "letter", "classify", "intake"]

#: Every task, in the order a person would meet them: find a job, judge it,
#: tailor for it, write to them, read the reply. One tuple rather than the
#: literal repeated at each call site — it was already written out in three
#: places (``cli llm providers``, ``cli llm stats``, ``GET /stats/llm``), and a
#: fourth task added to two of them is a /models page that silently cannot
#: configure the thing the CLI can.
TASKS: tuple[Task, ...] = ("intake", "tailor", "letter", "classify")

#: What each task puts in a prompt, in words a person can weigh before deciding
#: whether to send it to a given company. One entry per task, and
#: :func:`warnings` **raises** on a task that has no entry rather than guessing.
#:
#: Guessing is the trap this replaces. A default of "your entire Master CV"
#: describes a task that sends it and libels one that doesn't; a default of
#: "nothing much" does the reverse, which is far worse. Either way the author of
#: task five would never find out, because the wrong sentence only appears in
#: front of the user. Missing entry, loud failure, at import-adjacent time.
#:
#: ``intake`` earns its wording from its *second* call only: reading a pasted JD
#: sends nothing personal, scoring that JD against the CV sends all of it.
PROMPT_CONTENTS: dict[str, str] = {
    "tailor": "your entire Master CV - name, phone number, employment history",
    "letter": "your entire Master CV - name, phone number, employment history",
    "intake": (
        "the job description you pasted and, when you ask for a fit check, your "
        "entire Master CV - name, phone number, employment history"
    ),
    "classify": "the text of employer emails that matched one of your applications",
}

#: The tasks whose prompt contains the Master CV — see
#: ``tailor/prompt.py:system_prompt``, ``apply/letter.py:ModelLetterEngine`` and
#: ``intake/prompt.py:fit_system_prompt``. Derived from the table above rather
#: than maintained beside it: two hand-kept lists of "which tasks send the CV"
#: is one list too many, and the one nobody reads is the one that goes stale.
SENDS_MASTER_CV: tuple[str, ...] = tuple(
    task for task, sends in PROMPT_CONTENTS.items() if "Master CV" in sends
)


def blocker(task: Task) -> str:
    """Why ``task`` can't run on its configured backend, or '' if it can.

    A missing API key is knowable *now*, and saying so beats a queued task that
    dies a minute later with the same message — the same courtesy
    ``ApplyCfg.inbox_blocker`` extends, and the same shape.

    It is deliberately only that check. Whether the key is *valid*, or whether
    the account has credit, can only be discovered by spending a request; a
    pre-flight that pretended otherwise would just be a slower way to be wrong.
    """
    from jobpilot.config import get_config
    from jobpilot.llm.base import LlmError
    from jobpilot.llm.registry import api_key, provider_for

    name = get_config().llm.for_task(task)
    try:
        provider = provider_for(name)
    except LlmError as exc:
        return str(exc)
    if not api_key(name) and not provider.key_optional:
        return (
            f"{provider.label} is configured for {task}, but {provider.env_var} is not set in .env"
        )
    if provider.preflight is not None and (reason := provider.preflight()):
        return f"{provider.label} is configured for {task}, but {reason}"
    return ""


def warning_items(task: Task) -> list[dict]:
    """The data-use warnings for ``task`` as keys and values, not sentences.

    What the dashboard renders, in either language: ``policy`` names the
    ``DATA_POLICY`` entry (``""`` = no note on record for this provider), and
    the frontend owns the wording. :func:`warnings` is the English rendering of
    exactly these items, for the CLI — one source, so the two cannot disagree
    about *whether* to warn.

    Separate from :func:`blocker` on purpose: a blocker stops the work, a
    warning does not. Tailoring puts the entire Master CV in the prompt, so the
    user is entitled to know a provider's terms before it goes — and entitled to
    send it anyway. This reports; it never decides.
    """
    from jobpilot.config import get_config
    from jobpilot.llm.pricing import CHECKED_ON, DATA_POLICY, policy_key

    cfg = get_config().llm
    name = cfg.for_task(task)
    if task not in PROMPT_CONTENTS:
        raise KeyError(
            f"task {task!r} has no entry in llm.PROMPT_CONTENTS — add one saying what "
            "its prompt contains, so the data-use warning describes the real payload"
        )
    key = policy_key(name, paid_tier=cfg.paid_tier(name))
    if key is None:
        return [{"policy": "", "provider": name, "task": task, "url": "", "checked_on": ""}]
    note = DATA_POLICY[key]
    if not note.trains_on_input:
        return []
    return [
        {
            "policy": key,
            "provider": name,
            "task": task,
            "url": note.url,
            "checked_on": note.checked_on or CHECKED_ON,
        }
    ]


def warnings(task: Task) -> list[str]:
    """:func:`warning_items` as English sentences — the CLI's rendering."""
    from jobpilot.llm.pricing import DATA_POLICY

    payload = PROMPT_CONTENTS.get(task, "")
    out = []
    for item in warning_items(task):
        if not item["policy"]:
            out.append(
                f"No data-use note on record for provider {item['provider']!r}. This task "
                f"sends {payload} - read its terms before enabling it."
            )
            continue
        summary = DATA_POLICY[item["policy"]].summary
        out.append(
            f"{item['provider']}: {summary} This task sends {payload}. "
            f"{item['url']} (checked {item['checked_on']})."
        )
    return out
