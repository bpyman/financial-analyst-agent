"use client";

import { useId, type ReactNode } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  Rectangle,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import type { BarShapeProps } from "recharts/types/cartesian/Bar";
import type { DotItemDotProps } from "recharts/types/util/types";
import {
  barRows,
  lineRows,
  lineSeries,
  niceTicks,
  valueDomain,
  type BarRow,
  type LineRow,
  type LineSeries,
} from "@/lib/chart-data";
import { axisTick } from "@/lib/format";
import type { BarChartSpec, ChartSpec, LineChartSpec, ValueKind } from "@/lib/types";
import { SectionLabel } from "./ui";

/**
 * A trend line or comparison bars. Marks are placed from the server's numbers;
 * every amount written on or beside a mark is the server's string (ADR 0006).
 */
export function AnswerChart({ chart }: { chart: ChartSpec }) {
  const single = chart.kind === "line" && chart.series.length === 1 ? chart.series[0] : null;
  return (
    <figure
      aria-label={`${chart.title}: ${chart.metric_label}`}
      className="overflow-hidden rounded-xl border border-border bg-surface"
    >
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 px-4 pt-4 sm:px-5">
        <div className="min-w-0">
          <SectionLabel>{chart.title}</SectionLabel>
          <div className="mt-1 flex min-w-0 flex-wrap items-baseline gap-x-2 text-[15px] font-medium text-fg">
            {chart.metric_label}
            {single && <span className="truncate text-[13px] font-normal text-muted">{single}</span>}
          </div>
        </div>
        {chart.kind === "line" && chart.series.length > 1 && <Legend series={lineSeries(chart)} />}
      </header>
      <div className="px-1 pb-3 pt-4 sm:px-3">
        {chart.kind === "line" ? <TrendChart chart={chart} /> : <ComparisonChart chart={chart} />}
      </div>
      {chart.caption && (
        <figcaption className="border-t border-border bg-surface-2/40 px-4 py-2.5 text-xs leading-relaxed text-muted sm:px-5">
          {chart.caption}
        </figcaption>
      )}
    </figure>
  );
}

function Legend({ series }: { series: LineSeries[] }) {
  return (
    <ul aria-label="Series" className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted">
      {series.map(({ key, name, color }) => (
        <li key={key} className="flex items-center gap-2">
          <LineKey color={color} />
          {name}
        </li>
      ))}
    </ul>
  );
}

function LineKey({ color }: { color: string }) {
  return <span aria-hidden className="h-0.5 w-3.5 shrink-0 rounded-full" style={{ background: color }} />;
}

const AXIS_TICK = { fill: "var(--subtle)", fontSize: 11 } as const;
const GRID = "var(--border)";

function TrendChart({ chart }: { chart: LineChartSpec }) {
  const gradientId = useId().replace(/:/g, "");
  const series = lineSeries(chart);
  const rows = lineRows(chart);
  const values = rows.flatMap((row) => series.map(({ key }) => row[key] as number | null));
  const ticks = niceTicks(valueDomain(values, { zero: false }));
  const domain: [number, number] = [ticks[0], ticks[ticks.length - 1]];
  const endLabels = endLabelsFit(rows, series, domain) ? endLabelSides(rows, series) : null;
  const lone = series.length === 1 ? series[0] : null;
  return (
    <ComposedChart
      responsive
      data={rows}
      margin={{ top: 22, right: 20, bottom: 4, left: 4 }}
      style={{ width: "100%", height: 280 }}
    >
      {lone && (
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lone.color} stopOpacity={0.16} />
            <stop offset="100%" stopColor={lone.color} stopOpacity={0} />
          </linearGradient>
        </defs>
      )}
      <CartesianGrid vertical={false} stroke={GRID} />
      <XAxis
        dataKey="period"
        tickLine={false}
        axisLine={{ stroke: GRID }}
        tick={<PeriodTick />}
        interval={0}
        height={40}
        padding={{ left: 24, right: 24 }}
      />
      <YAxis
        tickFormatter={(value: number) => axisTick(value, chart.value_kind)}
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
        domain={domain}
        ticks={ticks}
        interval={0}
        width={56}
      />
      <Tooltip
        cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
        position={{ y: 0 }}
        offset={16}
        content={(props) => <TrendTooltip {...props} series={series} />}
        isAnimationActive={false}
      />
      {lone && (
        <Area
          dataKey={lone.key}
          type="linear"
          stroke="none"
          fill={`url(#${gradientId})`}
          baseValue={domain[0]}
          tooltipType="none"
          activeDot={false}
          isAnimationActive={false}
        />
      )}
      {series.map(({ key, color }) =>
        hasGap(rows, key) ? (
          // A missing quarter is bridged faintly, never drawn as a reported value.
          <Line
            key={`${key}-gap`}
            dataKey={key}
            type="linear"
            connectNulls
            stroke={color}
            strokeOpacity={0.45}
            strokeWidth={1.5}
            strokeDasharray="2 5"
            strokeLinecap="round"
            dot={false}
            activeDot={false}
            tooltipType="none"
            isAnimationActive={false}
          />
        ) : null,
      )}
      {series.map(({ key, color, name }) => (
        <Line
          key={key}
          name={name}
          dataKey={key}
          type="linear"
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          dot={(props: DotItemDotProps) => (
            <TrendDot
              key={`${key}-${props.index}`}
              {...props}
              seriesKey={key}
              color={color}
              labelSide={endLabels?.[key] ?? null}
            />
          )}
          activeDot={{ r: 5.5, fill: color, stroke: "var(--surface)", strokeWidth: 2 }}
          animationDuration={600}
        />
      ))}
    </ComposedChart>
  );
}

function hasGap(rows: LineRow[], key: string): boolean {
  const present = rows.map((row) => row[key] !== null);
  const first = present.indexOf(true);
  const last = present.lastIndexOf(true);
  return first >= 0 && present.slice(first, last + 1).includes(false);
}

/** End labels only when the latest points sit far enough apart to read. */
function endLabelsFit(rows: LineRow[], series: LineSeries[], [low, high]: [number, number]): boolean {
  const ends = series
    .map(({ key }) => rows.findLast((row) => row.last?.includes(key))?.[key])
    .filter((value): value is number => typeof value === "number")
    .sort((a, b) => a - b);
  const span = high - low || 1;
  return ends.every((value, index) => index === 0 || (value - ends[index - 1]) / span > 0.14);
}

/** Put each end label on the side its final segment leaves open. */
function endLabelSides(rows: LineRow[], series: LineSeries[]): Record<string, "above" | "below"> {
  const sides: Record<string, "above" | "below"> = {};
  for (const { key } of series) {
    const values = rows.map((row) => row[key]).filter((value): value is number => typeof value === "number");
    const [previous, last] = values.slice(-2);
    sides[key] = values.length > 1 && last < previous ? "below" : "above";
  }
  return sides;
}

function TrendDot({
  cx,
  cy,
  payload,
  seriesKey,
  color,
  labelSide,
}: DotItemDotProps & { seriesKey: string; color: string; labelSide: "above" | "below" | null }) {
  const row = payload as LineRow;
  if (typeof cx !== "number" || typeof cy !== "number" || row[seriesKey] === null) return <g />;
  const isLast = row.last?.includes(seriesKey) ?? false;
  return (
    <g>
      <circle cx={cx} cy={cy} r={4} fill={color} stroke="var(--surface)" strokeWidth={2} />
      {isLast && labelSide && (
        <text
          x={cx - 9}
          y={labelSide === "above" ? cy - 11 : cy + 19}
          textAnchor="end"
          fill="var(--fg)"
          fontSize={11.5}
          fontWeight={600}
          stroke="var(--surface)"
          strokeWidth={4}
          paintOrder="stroke"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {row.amounts[seriesKey]}
        </text>
      )}
    </g>
  );
}

/** "Mar 31, 2026" on two lines, so four quarters fit a phone. */
function PeriodTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const text = payload?.value ?? "";
  const split = text.lastIndexOf(", ");
  const [day, year] = split > 0 ? [text.slice(0, split), text.slice(split + 2)] : [text, ""];
  return (
    <text x={x} y={y} textAnchor="middle" fontSize={11} fill="var(--subtle)">
      <tspan x={x} dy={14} fill="var(--muted)">
        {day}
      </tspan>
      {year && (
        <tspan x={x} dy={13}>
          {year}
        </tspan>
      )}
    </text>
  );
}

function TrendTooltip({
  active,
  payload,
  label,
  series,
}: TooltipContentProps & { series: LineSeries[] }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as LineRow;
  return (
    <TooltipBox title={String(label ?? row.period)}>
      {series.map(({ key, name, color }) => (
        <div key={key} className="flex items-center gap-2.5">
          <LineKey color={color} />
          <span className="min-w-[4.5rem] text-[13px] font-semibold tabular-nums text-fg">
            {row.amounts[key] ?? <span className="font-normal text-subtle">—</span>}
          </span>
          <span className="truncate text-muted">{name}</span>
        </div>
      ))}
    </TooltipBox>
  );
}

function TooltipBox({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="max-w-[18rem] rounded-lg border border-border-strong bg-surface/95 px-3 py-2.5 text-xs shadow-xl shadow-black/25 backdrop-blur-sm">
      <div className="mb-1.5 text-[11px] font-medium text-subtle">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

const BAR_FILL = "var(--chart-1)";

function ComparisonChart({ chart }: { chart: BarChartSpec }) {
  const rows = barRows(chart);
  const ticks = niceTicks(
    valueDomain(
      rows.map((row) => (row.missing ? null : row.value)),
      { zero: true },
    ),
  );
  const props = { rows, ticks, kind: chart.value_kind, metric: chart.metric_label };
  return chart.horizontal ? <RankedBars {...props} /> : <ColumnBars {...props} />;
}

interface BarsProps {
  rows: BarRow[];
  ticks: number[];
  kind: ValueKind;
  metric: string;
}

const ROW_HEIGHT = 34;
const RANK_AXIS_WIDTH = 84;

/** Rank order top to bottom; bar length is the metric. */
function RankedBars({ rows, ticks, kind, metric }: BarsProps) {
  return (
    <BarChart
      responsive
      layout="vertical"
      data={rows}
      barCategoryGap={0}
      margin={{ top: 0, right: 72, bottom: 0, left: 4 }}
      style={{ width: "100%", height: rows.length * ROW_HEIGHT + 32 }}
    >
      <CartesianGrid horizontal={false} stroke={GRID} />
      <XAxis
        type="number"
        domain={[ticks[0], ticks[ticks.length - 1]]}
        ticks={ticks}
        interval={0}
        tickFormatter={(value: number) => axisTick(value, kind)}
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
        height={28}
      />
      <YAxis
        type="category"
        dataKey="name"
        tick={<RankTick rows={rows} />}
        tickLine={false}
        axisLine={{ stroke: GRID }}
        width={RANK_AXIS_WIDTH}
        interval={0}
      />
      <Tooltip
        cursor={{ fill: "var(--surface-2)", fillOpacity: 0.7 }}
        content={(props) => <BarTooltip {...props} metric={metric} />}
        isAnimationActive={false}
      />
      <Bar
        dataKey="value"
        barSize={16}
        shape={(props: BarShapeProps) => <BarShape {...props} rows={rows} horizontal />}
        activeBar={(props: BarShapeProps) => <BarShape {...props} rows={rows} horizontal />}
        animationDuration={600}
      />
    </BarChart>
  );
}

function ColumnBars({ rows, ticks, kind, metric }: BarsProps) {
  return (
    <BarChart
      responsive
      data={rows}
      margin={{ top: 24, right: 12, bottom: 0, left: 4 }}
      style={{ width: "100%", height: 260 }}
    >
      <CartesianGrid vertical={false} stroke={GRID} />
      <XAxis
        dataKey="name"
        tickLine={false}
        axisLine={{ stroke: GRID }}
        tick={{ fill: "var(--muted)", fontSize: 11.5 }}
        interval={0}
        height={28}
      />
      <YAxis
        domain={[ticks[0], ticks[ticks.length - 1]]}
        ticks={ticks}
        interval={0}
        tickFormatter={(value: number) => axisTick(value, kind)}
        tick={AXIS_TICK}
        tickLine={false}
        axisLine={false}
        width={56}
      />
      <Tooltip
        cursor={{ fill: "var(--surface-2)", fillOpacity: 0.7 }}
        content={(props) => <BarTooltip {...props} metric={metric} />}
        isAnimationActive={false}
      />
      <Bar
        dataKey="value"
        maxBarSize={48}
        shape={(props: BarShapeProps) => <BarShape {...props} rows={rows} />}
        activeBar={(props: BarShapeProps) => <BarShape {...props} rows={rows} />}
        animationDuration={600}
      />
    </BarChart>
  );
}

/**
 * One bar and its label, drawn together so a missing value (no bar) cannot
 * shift the labels of the bars after it.
 */
function BarShape({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  index,
  isActive,
  rows,
  horizontal = false,
}: BarShapeProps & { rows: BarRow[]; horizontal?: boolean }) {
  const row = rows[index];
  if (!row) return <g />;
  return (
    <g>
      {!row.missing && (
        <Rectangle
          x={x}
          y={y}
          width={width}
          height={height}
          radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
          fill={BAR_FILL}
          fillOpacity={isActive ? 0.8 : 1}
        />
      )}
      <BarLabel row={row} box={{ x, y, width, height }} horizontal={horizontal} />
    </g>
  );
}

/** The server's amount at the bar's end, or the muted reason a value is missing. */
function BarLabel({
  row,
  box: { x, y, width, height },
  horizontal,
}: {
  row: BarRow;
  box: { x: number; y: number; width: number; height: number };
  horizontal: boolean;
}) {
  const style = { fontVariantNumeric: "tabular-nums" } as const;
  const tone = row.missing
    ? { fill: "var(--subtle)", fontStyle: "italic" as const, fontWeight: 400 }
    : { fill: "var(--fg)", fontWeight: 500 };
  if (horizontal) {
    // Negative bars end at the left; their label sits beyond that end.
    const end = width < 0 ? x + width - 6 : x + width + 8;
    return (
      <text x={end} y={y + height / 2} dy="0.35em" textAnchor={width < 0 ? "end" : "start"} fontSize={11.5} style={style} {...tone}>
        {row.label}
      </text>
    );
  }
  const top = row.missing ? y - 8 : height < 0 ? y + 14 : y - 8;
  return (
    <text x={x + width / 2} y={top} textAnchor="middle" fontSize={11.5} style={style} {...tone}>
      {row.label}
    </text>
  );
}

/** "#1 AAPL": the rank in muted numerals, the ticker in full ink. */
function RankTick({
  x,
  y,
  payload,
  rows,
}: {
  x?: number;
  y?: number;
  payload?: { value: string; index: number };
  rows: BarRow[];
}) {
  const text = payload?.value ?? "";
  const match = /^(#\d+)\s+(.*)$/.exec(text);
  const missing = rows[payload?.index ?? -1]?.missing ?? false;
  const [rank, name] = match ? [match[1], match[2]] : ["", text];
  // Fixed columns so "#1" and "#10" line their tickers up.
  return (
    <g fontSize={11.5} fontFamily="var(--font-mono)">
      {rank && (
        <text x={(x ?? 0) - RANK_AXIS_WIDTH + 4} y={y} dy="0.35em" textAnchor="start" fill="var(--subtle)">
          {rank}
        </text>
      )}
      <text
        x={(x ?? 0) - 10}
        y={y}
        dy="0.35em"
        textAnchor="end"
        fontWeight={500}
        fill={missing ? "var(--subtle)" : "var(--fg)"}
      >
        {name}
      </text>
    </g>
  );
}

function BarTooltip({
  active,
  payload,
  metric,
}: TooltipContentProps & { metric: string }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as BarRow;
  return (
    <TooltipBox title={row.name}>
      <div className="flex items-baseline gap-2.5">
        {row.missing ? (
          <span className="text-[13px] font-medium text-warning">{row.label}</span>
        ) : (
          <span className="text-[13px] font-semibold tabular-nums text-fg">{row.amount}</span>
        )}
        <span className="truncate text-muted">{metric}</span>
      </div>
      {row.period && <div className="text-[11px] tabular-nums text-subtle">{row.period}</div>}
    </TooltipBox>
  );
}
