/**
 * Display names for the raw keys that come out of the crawler.
 *
 * The database stores what the parsers produce — `no_jd`, `ci/cd`,
 * `weworkremotely` — and that is the right thing for it to store. But a chart
 * axis is prose, and `thin_jd` on an axis reads as a leaked column name. The
 * translation belongs here, at the edge, so nothing downstream is tempted to
 * "clean up" the stored value itself.
 *
 * Unknown keys fall back to title case rather than disappearing: a new source
 * or a new quality flag must still be readable the day it lands, before anyone
 * has added it to a map.
 */

import { useMemo } from "react";
import { useI18n } from "@/i18n";
import { dict } from "@/i18n/dict";

const SOURCE_NAMES: Record<string, string> = {
  itviec: "ITviec",
  topcv: "TopCV",
  vietnamworks: "VietnamWorks",
  linkedin: "LinkedIn",
  weworkremotely: "WeWorkRemotely",
  arbeitnow: "Arbeitnow",
  greenhouse: "Greenhouse",
  lever: "Lever",
  topdev: "TopDev",
};

/**
 * Where each source lives, so a chip can link to the board it crawls.
 *
 * The homepage, not a search URL: what a query looks like is the scraper's
 * business and changes with it, while "which site is this" is the question a
 * link next to a source name answers.
 */
const SOURCE_HOMES: Record<string, string> = {
  itviec: "https://itviec.com",
  topcv: "https://www.topcv.vn",
  vietnamworks: "https://www.vietnamworks.com",
  // The scraper never touches LinkedIn — it reads Job Alert mail — but the
  // alerts are configured on LinkedIn, so that is where the link should go.
  linkedin: "https://www.linkedin.com/jobs",
  weworkremotely: "https://weworkremotely.com",
  arbeitnow: "https://www.arbeitnow.com",
  greenhouse: "https://www.greenhouse.io",
  lever: "https://www.lever.co",
  topdev: "https://topdev.vn",
};

/** Homepage of the board behind a source key, or `null` if we don't know one. */
export function sourceHome(key: string): string | null {
  return SOURCE_HOMES[key.toLowerCase()] ?? null;
}

// Technologies whose casing is not title case. Everything else — react, docker,
// kafka — title-cases correctly, so the map only carries the exceptions.
const SKILL_NAMES: Record<string, string> = {
  ai: "AI",
  api: "API",
  aws: "AWS",
  "ci/cd": "CI/CD",
  css: "CSS",
  gcp: "GCP",
  graphql: "GraphQL",
  html: "HTML",
  ios: "iOS",
  javascript: "JavaScript",
  jquery: "jQuery",
  k8s: "Kubernetes",
  ml: "ML",
  mongodb: "MongoDB",
  mysql: "MySQL",
  nodejs: "Node.js",
  "node.js": "Node.js",
  oop: "OOP",
  php: "PHP",
  postgresql: "PostgreSQL",
  mariadb: "MariaDB",
  qa: "QA",
  rest: "REST",
  sql: "SQL",
  typescript: "TypeScript",
  ui: "UI",
  ux: "UX",
};

function titleCase(key: string): string {
  return key
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const lookup = (map: Record<string, string>) => (key: string) =>
  map[key.toLowerCase()] ?? titleCase(key);

/**
 * Source and skill names are proper nouns — "ITviec" and "PostgreSQL" read the
 * same in both languages — so they need no language and stay plain functions.
 */
export const sourceLabel = lookup(SOURCE_NAMES);
export const skillLabel = lookup(SKILL_NAMES);

/**
 * Quality flags and seniority *are* prose, so they go through the dictionary.
 *
 * Exported as a hook rather than as `qualityLabel(key, lang)` so that a call
 * site cannot forget to pass the language and silently render English inside a
 * Vietnamese page. The old language-free `qualityLabel`/`levelLabel` exports are
 * gone on purpose: removing them turns every stale call site into a compile
 * error instead of a translation gap nobody notices.
 */
export function useLabels() {
  const { lang } = useI18n();
  return useMemo(() => {
    const table = dict.labels[lang] as Record<string, string>;
    // Same fallback the file has always promised: a quality flag or a level
    // that lands before anyone adds it to the dictionary must still be
    // readable, so an unknown key title-cases instead of vanishing.
    const prefixed = (prefix: string) => (key: string) =>
      table[`${prefix}_${key.toLowerCase()}`] ?? titleCase(key);
    return {
      sourceLabel,
      skillLabel,
      qualityLabel: prefixed("quality"),
      levelLabel: prefixed("level"),
    };
  }, [lang]);
}
