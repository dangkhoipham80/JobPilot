// Display helpers. Interface voice: plain, specific, end-user facing.

import { useMemo } from "react";
import { useI18n, type Lang } from "@/i18n";
import { dict } from "@/i18n/dict";

/** BCP-47 tag for `Intl`, so dates follow the language the UI is in. */
const LOCALE: Record<Lang, string> = { vi: "vi-VN", en: "en-US" };

/**
 * The date/time helpers, bound to one language.
 *
 * Built as a factory rather than reading a module-level "current language",
 * because a module global would not re-render anything when the language flips:
 * a table of "3h ago" would stay English until something else happened to
 * invalidate it. Going through `useFormat()` makes the dependency explicit and
 * lets React do what it already does well.
 */
export function makeFormat(lang: Lang) {
  const t = (key: keyof typeof dict.format.en, n?: number): string => {
    const raw = dict.format[lang][key];
    return n === undefined ? raw : raw.replace("{n}", String(n));
  };
  const locale = LOCALE[lang];

  function relativeTime(iso: string | null): string {
    if (!iso) return t("absent");
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return t("absent");
    const diff = Date.now() - then;
    const mins = Math.round(diff / 60000);
    if (mins < 1) return t("justNow");
    if (mins < 60) return t("minutesAgo", mins);
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return t("hoursAgo", hrs);
    const days = Math.round(hrs / 24);
    if (days < 30) return t("daysAgo", days);
    return new Date(iso).toLocaleDateString(locale);
  }

  function shortDay(iso: string): string {
    // "2026-07-10" -> "Jul 10" (en) / "10 thg 7" (vi)
    const d = new Date(iso + "T00:00:00");
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(locale, { month: "short", day: "numeric" });
  }

  /** "today 14:32" / "Jul 26 09:05" — for "when exactly did that crawl run?". */
  function clockTime(iso: string | null): string {
    if (!iso) return t("absent");
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return t("absent");
    const time = d.toLocaleTimeString(locale, {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    const day =
      d.toDateString() === new Date().toDateString()
        ? t("today")
        : d.toLocaleDateString(locale, { month: "short", day: "numeric" });
    return `${day} ${time}`;
  }

  return { relativeTime, shortDay, clockTime };
}

/** `const fmt = useFormat()`, then `fmt.relativeTime(job.posted_at)`. */
export function useFormat() {
  const { lang } = useI18n();
  return useMemo(() => makeFormat(lang), [lang]);
}

export function matchPercent(score: number): number {
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}

export function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
