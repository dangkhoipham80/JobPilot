import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import {
  Activity,
  Briefcase,
  BookOpen,
  Building2,
  Cpu,
  DatabaseBackup,
  TrendingUp,
  FileText,
  LayoutDashboard,
  Moon,
  Plane,
  Send,
  Settings2,
  Sun,
} from "lucide-react";
import { LANG_NAMES, useI18n, useT, type Lang } from "@/i18n";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

// `key` indexes the nav namespace; the visible string is resolved at render so
// it follows the language switch.
const NAV = [
  { to: "/", key: "deck", icon: LayoutDashboard, end: true },
  { to: "/jobs", key: "jobs", icon: Briefcase, end: false },
  { to: "/cv", key: "cv", icon: FileText, end: false },
  { to: "/applications", key: "applications", icon: Send, end: false },
  { to: "/companies", key: "companies", icon: Building2, end: false },
  { to: "/runs", key: "runs", icon: Activity, end: false },
  { to: "/market", key: "market", icon: TrendingUp, end: false },
  { to: "/models", key: "models", icon: Cpu, end: false },
  { to: "/backup", key: "backup", icon: DatabaseBackup, end: false },
  { to: "/settings", key: "settings", icon: Settings2, end: false },
  { to: "/guide", key: "guide", icon: BookOpen, end: false },
] as const;

export function Layout({ live, children }: { live: boolean; children: ReactNode }) {
  const { theme, toggle } = useTheme();
  const t = useT("nav");

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r bg-surface/60 px-3 py-5">
        <div className="flex items-center gap-2 px-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-accent-ink">
            <Plane size={17} className="-rotate-45" />
          </span>
          <span className="font-display text-lg font-semibold tracking-tight">JobPilot</span>
        </div>

        <nav className="mt-8 flex flex-col gap-1">
          {NAV.map(({ to, key, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-accent/12 text-ink [box-shadow:inset_2px_0_0_rgb(var(--accent))]"
                    : "text-ink-muted hover:bg-surface-2 hover:text-ink",
                )
              }
            >
              <Icon size={17} />
              {t(key)}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto px-2 text-[11px] leading-relaxed text-ink-muted">
          {t("tagline")}
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-bg/80 px-6 backdrop-blur">
          <LiveIndicator live={live} />
          <div className="flex items-center gap-1">
            <LanguageToggle />
            <button
              onClick={toggle}
              aria-label={theme === "dark" ? t("toLight") : t("toDark")}
              className="grid h-8 w-8 place-items-center rounded-lg text-ink-muted hover:bg-surface-2 hover:text-ink"
            >
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </header>

        {/* Full-bleed on purpose: this is a local single-user control plane on a
            desktop monitor, and a centered `max-w-6xl` column left ~600px of dead
            gutter on a 1920 screen while the job table truncated its own titles.
            Long-form prose keeps its own reading measure (see Markdown). */}
        <main className="w-full flex-1 px-6 py-6 2xl:px-8">{children}</main>
      </div>
    </div>
  );
}

/**
 * VI / EN as a two-slot segmented control rather than a dropdown.
 *
 * With exactly two options a select costs a click to discover what the other
 * one even is, while both labels fit in the space the closed dropdown would
 * have taken. `aria-pressed` carries the state that the highlight shows.
 */
function LanguageToggle() {
  const { lang, setLang } = useI18n();
  const t = useT("nav");
  const options: Lang[] = ["vi", "en"];

  return (
    <div
      role="group"
      aria-label={t("language")}
      className="flex items-center rounded-lg border p-0.5 text-[11px] font-semibold"
    >
      {options.map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          title={LANG_NAMES[code]}
          className={cn(
            "rounded-[5px] px-1.5 py-0.5 uppercase tracking-wide transition-colors",
            lang === code
              ? "bg-accent/15 text-accent"
              : "text-ink-muted hover:bg-surface-2 hover:text-ink",
          )}
        >
          {code}
        </button>
      ))}
    </div>
  );
}

function LiveIndicator({ live }: { live: boolean }) {
  const t = useT("nav");
  return (
    <div className="flex items-center gap-2 text-xs font-medium">
      <span className="relative flex h-2 w-2">
        {live && (
          <span className="absolute inline-flex h-full w-full animate-beacon rounded-full bg-live" />
        )}
        <span
          className={cn("relative inline-flex h-2 w-2 rounded-full", live ? "bg-live" : "bg-ink-muted/50")}
        />
      </span>
      <span className={cn("font-mono uppercase tracking-widest", live ? "text-live" : "text-ink-muted")}>
        {live ? t("live") : t("offline")}
      </span>
    </div>
  );
}
