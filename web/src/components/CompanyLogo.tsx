import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * An employer's logo, or its initials when there is none (yet).
 *
 * The picture is the cached copy the API serves (`/api/logos/<hash>`), never a
 * board's CDN: see `jobpilot/companies/logos.py`. Initials are a UI fallback,
 * not a stored logo — a company whose logo arrives after the next crawl simply
 * switches from one to the other.
 *
 * The tint is derived from the name, so one employer keeps one colour across
 * every page, and it is drawn from the app's own ink/accent tokens at low
 * alpha rather than a rainbow: thirty coloured squares down a job list would
 * shout louder than the titles beside them.
 */
export function CompanyLogo({
  name,
  logo,
  size = 28,
  className,
}: {
  name: string;
  logo?: string | null;
  size?: number;
  className?: string;
}) {
  const [broken, setBroken] = useState(false);
  const style = { width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.38)) };

  if (logo && !broken) {
    return (
      <img
        src={logo}
        alt=""
        loading="lazy"
        onError={() => setBroken(true)}
        style={style}
        className={cn("shrink-0 rounded-md border border-border bg-white object-contain p-0.5", className)}
      />
    );
  }
  const tones = ["bg-accent/15 text-accent", "bg-good/15 text-good", "bg-live/15 text-live", "bg-ink/10 text-ink"];
  return (
    <span
      aria-hidden
      style={style}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-md font-semibold uppercase",
        tones[hash(name) % tones.length],
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}

/** "Công ty TNHH Giải pháp Trí tuệ Số" → "GT", "Acme Corp" → "AC". */
export function initials(name: string): string {
  const skip = new Set(["công", "ty", "tnhh", "cổ", "phần", "cp", "jsc", "ltd", "inc", "co", "the", "corp"]);
  const words = name
    .split(/[\s,.()&-]+/)
    .filter((w) => w && !skip.has(w.toLowerCase()));
  const picked = (words.length ? words : name.split(/\s+/)).slice(0, 2);
  return picked.map((w) => [...w][0] ?? "").join("") || "?";
}

function hash(text: string): number {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return Math.abs(h);
}
