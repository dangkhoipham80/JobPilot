"""The market half of a CV critique — counted, never asked of a model.

Every number the critique page shows comes from here, out of the crawled jobs in
Postgres, with its denominator (``analytics/CLAUDE.md``: a share without
``covered``/``total`` describes which boards tag their ads, not the market). The
model is handed this snapshot to reason over, but it is told not to quote
figures: the page prints them next to its text, from this dict, so a figure on
screen is always one that was counted.

**This describes the corpus JobPilot crawled, not the Vietnamese job market.**
The crawl runs on the user's own keywords, so it leans hard towards whatever they
searched for; the snapshot says how many jobs it rests on, and the role filter
narrows it further.
"""

from __future__ import annotations

import re
from collections import Counter

from jobpilot.analytics.market import MIN_SAMPLE, by_level, top_skills
from jobpilot.crawler.skills import canonical
from jobpilot.cv.schema import BulletsSection, CvDocument
from jobpilot.tailor.guard import master_text

#: Target roles, matched against the job **title**. A title is the one field
#: every source has (LinkedIn carries no skills), and it is what a recruiter
#: means by "role". Stack words count for backend because a "Java Developer"
#: ad is a backend ad; a title can fall into several roles, and does.
ROLE_PATTERNS: dict[str, str] = {
    "backend": r"back[\s-]?end|\bjava\b|\.net|golang|\bgo\b|\bphp\b|node|python|ruby|spring",
    "fullstack": r"full[\s-]?stack",
    "frontend": r"front[\s-]?end|react|angular|\bvue\b|\bui\b",
    "mobile": r"mobile|android|\bios\b|flutter|react native",
    "ai": r"\bai\b|machine learning|\bml\b|\bllm\b|genai|deep learning",
    "devops": r"devops|\bsre\b|cloud|platform|infrastructure",
    "data": r"\bdata\b|analytics|\bbi\b",
    "game": r"\bgame|unity|unreal",
}

#: How many of the most demanded skills the snapshot carries.
TOP_SKILLS = 20


def role_matches(role: str, title: str) -> bool:
    """A preset key uses its pattern; anything else is a phrase the title must contain."""
    role = role.strip().lower()
    if not role:
        return True
    pattern = ROLE_PATTERNS.get(role) or re.escape(role)
    return re.search(pattern, title or "", re.I) is not None


def mentions(text: str, term: str) -> bool:
    """Whole-term match: "java" not inside "javascript", "c#" and "next.js" intact."""
    term = term.strip().lower()
    if not term:
        return False
    return re.search(rf"(?<![\w.#+]){re.escape(term)}(?![\w#+])", text) is not None


def cv_skill_names(doc: CvDocument) -> list[str]:
    """The comma-separated names in the CV's skills-like bullet sections."""
    names: list[str] = []
    for section in doc.sections:
        if not isinstance(section, BulletsSection) or "skill" not in section.key.lower():
            continue
        for item in section.items:
            for part in re.split(r",|\band\b", item.text):
                name = re.sub(r"[*`]", "", part).strip(" .")
                if name and name not in names:
                    names.append(name)
    return names


def snapshot(payloads: list[dict], doc: CvDocument, role: str = "") -> dict:
    """What the jobs for ``role`` ask for, set against what the CV shows.

    ``payloads`` are job payloads as stored (``title``, ``skills_canonical``,
    ``level``…). Returns plain JSON so it can be stored beside the critique as
    the exact evidence the model was given.
    """
    jobs = [p for p in payloads if role_matches(role, p.get("title") or "")]
    cv_text = master_text(doc).lower()

    skills = top_skills(jobs, limit=TOP_SKILLS).as_dict()
    for row in skills["rows"]:
        row["on_cv"] = mentions(cv_text, row["key"])

    # How often the skills the CV lists are asked for, so a line nobody asks
    # for is visible. Counted on the same denominator as `skills` above.
    asked: Counter[str] = Counter()
    for p in jobs:
        asked.update(set(p.get("skills_canonical") or []))
    cv_skills = []
    for name in cv_skill_names(doc):
        key = canonical(name)
        cv_skills.append({"name": name, "key": key, "count": asked.get(key, 0) if key else 0})

    return {
        "role": role.strip().lower(),
        "jobs": len(jobs),
        "total_jobs": len(payloads),
        "min_sample": MIN_SAMPLE,
        "skills": skills,
        "levels": by_level(jobs).as_dict(),
        "cv_skills": cv_skills,
    }


def render(snap: dict) -> str:
    """The snapshot as prompt text — counts included, so the model can weigh them."""
    skills = snap["skills"]
    lines = [
        "MARKET SNAPSHOT (crawled job ads, not the whole market)",
        f"target role: {snap['role'] or 'any'}",
        f"jobs matching the role: {snap['jobs']} of {snap['total_jobs']} crawled",
        f"jobs that list skills: {skills['covered']} of {snap['jobs']}",
    ]
    if snap["jobs"] < snap["min_sample"]:
        lines.append("WARNING: too few jobs for the counts below to mean much.")
    lines.append("most requested skills (jobs listing it; on_cv = the CV mentions it):")
    for row in skills["rows"]:
        mark = "on_cv" if row["on_cv"] else "NOT on cv"
        lines.append(f"  - {row['key']}: {row['count']}  [{mark}]")
    levels = snap["levels"]
    if levels["rows"]:
        lines.append(f"seniority asked for ({levels['covered']} of {snap['jobs']} state one):")
        lines += [f"  - {r['key']}: {r['count']}" for r in levels["rows"]]
    if snap["cv_skills"]:
        lines.append("skills the CV lists, and how many of these jobs ask for each:")
        lines += [f"  - {s['name']}: {s['count']}" for s in snap["cv_skills"]]
    return "\n".join(lines)
