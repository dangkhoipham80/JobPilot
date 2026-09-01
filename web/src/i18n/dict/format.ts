import { ns } from "../ns";

/**
 * Units for `lib/format.ts`.
 *
 * Vietnamese has no plural inflection, so "1 giờ trước" and "5 giờ trước" share
 * a form — which is why one `{n}`-shaped string per unit is enough here and no
 * plural-rule engine is warranted. English gets away with it too because every
 * unit is abbreviated (`5m ago`, `3h ago`) and abbreviations don't pluralise.
 */
export const format = ns({
  en: {
    justNow: "just now",
    minutesAgo: "{n}m ago",
    hoursAgo: "{n}h ago",
    daysAgo: "{n}d ago",
    today: "today",
    /** Stand-in for a value we don't have. */
    absent: "—",
  },
  vi: {
    justNow: "vừa xong",
    minutesAgo: "{n} phút trước",
    hoursAgo: "{n} giờ trước",
    daysAgo: "{n} ngày trước",
    today: "hôm nay",
    absent: "—",
  },
});
