"use client";

import { createContext, useContext } from "react";

/**
 * Which answer a region belongs to, so the same region in a later answer
 * ("Answer table") gets a name of its own among the page's landmarks.
 * Empty for the first answer.
 */
export const AnswerScope = createContext("");

export function useRegionName(name: string): string {
  const scope = useContext(AnswerScope);
  return scope ? `${name} (${scope})` : name;
}
