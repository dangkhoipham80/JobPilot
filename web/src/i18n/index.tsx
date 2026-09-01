/**
 * Language switching for the dashboard.
 *
 * Vietnamese is the default: this is a single-user control plane and the user
 * is Vietnamese. English stays a first-class second language because half the
 * vocabulary on screen (`DISCOVERED`, `Greenhouse`, `thin_jd`) is English in the
 * database anyway, and because the project's own screenshots are in English.
 *
 * Deliberately not `react-i18next`: the app carries seven runtime dependencies
 * on purpose, the copy is a fixed two-language table with no pluralisation
 * rules worth modelling (Vietnamese has no plural inflection), and a typed
 * `Record` gives compile-time key checking that a runtime lookup by string
 * would not. See `ns.ts` for the parity guarantee.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { dict, type NamespaceName } from "./dict";

export type Lang = "vi" | "en";

const KEY = "jobpilot-lang";

/** Values spliced into a string's `{placeholder}` slots. */
export type Vars = Record<string, string | number>;

export const LANG_NAMES: Record<Lang, string> = {
  vi: "Tiếng Việt",
  en: "English",
};

/**
 * Stored preference, or Vietnamese.
 *
 * Read once at module scope so the very first paint is already in the right
 * language — resolving this inside an effect would flash English for a frame.
 */
function stored(): Lang {
  try {
    return localStorage.getItem(KEY) === "en" ? "en" : "vi";
  } catch {
    // Private-mode / storage-disabled browsers: fall back rather than crash.
    return "vi";
  }
}

interface I18nValue {
  lang: Lang;
  setLang: (next: Lang) => void;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(stored);

  const setLang = useCallback((next: Lang) => {
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // Preference just won't survive a reload; the switch still works.
    }
    setLangState(next);
  }, []);

  // `lang` on <html> is what screen readers and the browser's own translation
  // prompt read. Keeping it in sync matters more than it looks: with it wrong,
  // Chrome offers to translate a page that is already in the user's language.
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  // Follow the preference if another tab flips it, same as the theme toggle.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) setLangState(e.newValue === "en" ? "en" : "vi");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}

/** `"Đã tìm thấy {count} tin"` + `{count: 12}` → `"Đã tìm thấy 12 tin"`. */
function interpolate(raw: string, vars: Vars): string {
  return raw.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in vars ? String(vars[name]) : whole,
  );
}

/**
 * Translator bound to one namespace: `const t = useT("jobs")`, then `t("title")`.
 *
 * Namespaced rather than one flat table so that page-sized chunks of copy stay
 * in page-sized files, and so two pages can both own a key called `title`.
 *
 * A missing Vietnamese string falls back to English rather than rendering
 * blank — `ns()` makes that unreachable through the type system, but a stale
 * key surviving a refactor should degrade to readable, not to emptiness.
 */
export function useT<N extends NamespaceName>(name: N) {
  const { lang } = useI18n();
  return useMemo(() => {
    const table = dict[name][lang] as Record<string, string>;
    const fallback = dict[name].en as Record<string, string>;
    return (key: keyof (typeof dict)[N]["en"], vars?: Vars): string => {
      const k = key as string;
      // `String(k)` and not `k`: the usual call is `t("title")`, but several
      // sites do `t(SOME_MAP[value])`, and a value the map has no entry for
      // makes `key` **undefined** — at which point `?? k` hands back `undefined`
      // and React renders nothing at all. Degrading to a visible token keeps the
      // promise above honest; silently blank is the failure mode to avoid.
      const raw = table[k] ?? fallback[k] ?? String(k);
      return vars ? interpolate(raw, vars) : raw;
    };
  }, [name, lang]);
}
