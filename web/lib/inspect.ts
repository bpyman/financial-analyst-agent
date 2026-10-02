import type { DisplayTable } from "./types";

/**
 * The evidence inspector's options in the order the table shows its figures
 * (sorted or pivoted as on screen), then any source no cell names: the facts a
 * derived or calculated figure came from.
 */
export function inspectorOrder(count: number, table: DisplayTable | null, rowOrder: number[] | null): number[] {
  const seen = new Set<number>();
  const order: number[] = [];
  const rows = rowOrder ?? table?.rows.map((_, index) => index) ?? [];
  for (const row of rows) {
    for (const index of table?.evidence?.[row] ?? []) {
      if (index !== null && index < count && !seen.has(index)) {
        seen.add(index);
        order.push(index);
      }
    }
  }
  for (let index = 0; index < count; index += 1) if (!seen.has(index)) order.push(index);
  return order;
}
