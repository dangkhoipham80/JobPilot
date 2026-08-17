import { useState } from "react";
import { sourceColor } from "@/components/charts/palette";
import { sourceLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

/**
 * The job board's own mark, so a source is recognisable before it is read.
 *
 * The logos are **vendored** into `web/public/logos/` rather than hotlinked.
 * Hotlinking looked cheaper until the URLs were checked: `/favicon.ico` serves
 * the SPA's HTML on ITviec, 404s on Greenhouse and Lever, and returns zero
 * bytes on TopCV, Arbeitnow and TopDev — and the URLs that *do* work carry
 * cache-busting hashes (`679a83f2…_gh_Icon`, `/uploads/2026/03/18/`) that will
 * rotate without warning. A logo that silently stops loading months later is
 * the failure mode this repo keeps paying for; a checked-in 500-byte PNG has
 * no such day. It also keeps a local-only dashboard from firing eight
 * cross-origin requests every render.
 *
 * Sources with no vendored file fall back to a monogram in the source's own
 * palette hue — the same colour the charts give it — so a board added tomorrow
 * is still identifiable today, and a broken file degrades to that rather than
 * to a browser's broken-image glyph.
 */

/** Keys with a file in `web/public/logos/`. Anything else skips the request
 *  entirely instead of 404ing once per render. */
const HAVE_LOGO = new Set([
  "itviec",
  "topcv",
  "vietnamworks",
  "linkedin",
  "weworkremotely",
  "arbeitnow",
  "greenhouse",
  "lever",
  "topdev",
]);

export function SourceIcon({
  source,
  size = 18,
  className,
}: {
  source: string;
  size?: number;
  className?: string;
}) {
  const key = source.toLowerCase();
  const [broken, setBroken] = useState(false);
  const box = { width: size, height: size };

  if (!HAVE_LOGO.has(key) || broken) {
    return (
      <span
        aria-hidden
        className={cn(
          "inline-flex shrink-0 items-center justify-center rounded-[4px] font-semibold uppercase leading-none text-white",
          className,
        )}
        style={{ ...box, background: sourceColor(key), fontSize: size * 0.55 }}
      >
        {key.slice(0, 1)}
      </span>
    );
  }

  return (
    <img
      src={`/logos/${key}.png`}
      alt=""
      aria-hidden
      loading="lazy"
      onError={() => setBroken(true)}
      className={cn("shrink-0 rounded-[3px] object-contain", className)}
      style={box}
      title={sourceLabel(source)}
    />
  );
}
