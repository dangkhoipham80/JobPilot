import { ns } from "../ns";

/**
 * Prose names for raw keys out of the crawler.
 *
 * Only the keys that are *descriptions* live here. Source names (`ITviec`,
 * `Greenhouse`) and skill names (`PostgreSQL`, `CI/CD`) are proper nouns and
 * stay in `lib/labels.ts` untranslated — "Node.js" is Node.js in Vietnamese,
 * and a translated brand name on a chart axis would be worse than useless.
 *
 * Seniority is the interesting case: the Vietnamese job market uses the English
 * ladder verbatim in postings ("tuyển Senior Backend"), so translating `senior`
 * to "cao cấp" would name a rung nobody advertises. Level labels therefore keep
 * their English form in both languages, with only `middle` normalised.
 */
export const labels = ns({
  en: {
    quality_clean: "Clean",
    quality_no_jd: "No description",
    quality_thin_jd: "Thin description",
    quality_stale: "Stale posting",
    quality_undated: "No posting date",

    level_intern: "Intern",
    level_fresher: "Fresher",
    level_junior: "Junior",
    level_middle: "Mid-level",
    level_senior: "Senior",

    /** Whose move it is, from `lib/statuses.ts`. */
    actor_you: "You",
    actor_agent: "Agent",
    actor_done: "Done",
  },
  vi: {
    quality_clean: "Đầy đủ",
    quality_no_jd: "Không có mô tả",
    quality_thin_jd: "Mô tả sơ sài",
    quality_stale: "Tin đã cũ",
    quality_undated: "Không rõ ngày đăng",

    level_intern: "Intern",
    level_fresher: "Fresher",
    level_junior: "Junior",
    level_middle: "Middle",
    level_senior: "Senior",

    actor_you: "Bạn",
    actor_agent: "Agent",
    actor_done: "Xong",
  },
});
