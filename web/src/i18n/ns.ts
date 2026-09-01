/**
 * One namespace of UI copy, in both languages.
 *
 * `en` is the source of truth for the *key set*: `vi` is typed as a mapped type
 * over `keyof T`, so TypeScript refuses a namespace where a Vietnamese string is
 * missing or where a stray key exists that English never had. That is the whole
 * point of the helper — a half-translated dictionary is exactly the bug this
 * feature exists to prevent, and `tsc --noEmit` already runs in `npm run build`,
 * so the check costs nothing extra at review time.
 *
 * Lives in its own module rather than in `index.tsx` because the dictionary
 * files import it while `index.tsx` imports the dictionary: sharing one module
 * would close that loop into an import cycle.
 */
export interface Namespace<T extends Record<string, string> = Record<string, string>> {
  en: T;
  vi: { [K in keyof T]: string };
}

export function ns<T extends Record<string, string>>(entries: Namespace<T>): Namespace<T> {
  return entries;
}
