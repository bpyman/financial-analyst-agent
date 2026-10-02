"use client";

import { createContext, useContext } from "react";

/**
 * Opens an evidence item in the answer's inspector: a table cell, a bar, or a
 * trend point calls it with its evidence index. Null outside an answer.
 */
export const InspectContext = createContext<((index: number) => void) | null>(null);

export function useInspect(): ((index: number) => void) | null {
  return useContext(InspectContext);
}
