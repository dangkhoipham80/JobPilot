import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { sourceColor } from "@/components/charts/palette";
import { TooltipBox, axisColor } from "@/components/charts/ChartFrame";
import { useT } from "@/i18n";
import { sourceLabel } from "@/lib/labels";

// Magnitude by identity → horizontal bars, one fixed hue per source (color
// follows the entity). Counts are direct-labeled, so no legend needed.
//
// Axis ticks are the boards' own names in both languages — but they go through
// `sourceLabel`, not `titleCase`. Title-casing a raw key invents a spelling the
// board does not use: `itviec` → "Itviec", `weworkremotely` → "Wework remotely".
// `sourceLabel` carries the real capitalisation and falls back to title case for
// a source that lands before anyone adds it to the map.
export function BySourceChart({ data }: { data: Record<string, number> }) {
  const t = useT("dashboard");
  const rows = Object.entries(data)
    .map(([source, count]) => ({ source, count }))
    .sort((a, b) => b.count - a.count);

  if (rows.length === 0) {
    return (
      <div className="grid h-24 place-items-center text-sm text-ink-muted">{t("noJobsYet")}</div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={Math.max(rows.length * 44, 88)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 28, top: 4, bottom: 4 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="source"
          axisLine={false}
          tickLine={false}
          // Fits the longest source label ("Weworkremotely"); at 92 it lost its
          // first letter, which reads as a typo rather than as clipping.
          width={110}
          tick={{ fill: axisColor(), fontSize: 12 }}
          tickFormatter={sourceLabel}
        />
        <Tooltip
          cursor={{ fill: "rgba(120,120,120,0.08)" }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TooltipBox
                label={sourceLabel(String(payload[0].payload.source))}
                rows={[
                  {
                    key: t("tipJobs"),
                    value: payload[0].value as number,
                    color: sourceColor(String(payload[0].payload.source)),
                  },
                ]}
              />
            ) : null
          }
        />
        <Bar dataKey="count" radius={[4, 4, 4, 4]} barSize={18} isAnimationActive={false}>
          {rows.map((r) => (
            <Cell key={r.source} fill={sourceColor(r.source)} />
          ))}
          <LabelList
            dataKey="count"
            position="right"
            className="fill-ink"
            style={{ fontSize: 12, fontVariantNumeric: "tabular-nums" }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
