/**
 * The namespace registry.
 *
 * Every namespace is listed here once; `useT("jobs")` type-checks against this
 * object, so a typo in a namespace name is a compile error rather than a blank
 * screen. Page-sized namespaces keep each file reviewable and let two pages own
 * the same key name (`title`, `empty`) without colliding.
 */
import { applications } from "./applications";
import { backup } from "./backup";
import { common } from "./common";
import { cv } from "./cv";
import { dashboard } from "./dashboard";
import { format } from "./format";
import { guide } from "./guide";
import { jobs } from "./jobs";
import { labels } from "./labels";
import { market } from "./market";
import { models } from "./models";
import { nav } from "./nav";
import { review } from "./review";
import { runs } from "./runs";
import { settings } from "./settings";
import { statuses } from "./statuses";
import { task } from "./task";

export const dict = {
  applications,
  backup,
  common,
  cv,
  dashboard,
  format,
  guide,
  jobs,
  labels,
  market,
  models,
  nav,
  review,
  runs,
  settings,
  statuses,
  task,
};

export type NamespaceName = keyof typeof dict;
