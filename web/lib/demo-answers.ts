import { readPresentation } from "./api";
import type { Presentation } from "./types";

/**
 * Each guided story's recorded answer (demo-answers.json, written from the
 * recorded runtime by scripts/record_demo_answers.py). While the hosted API
 * wakes, a clicked story shows its answer at once, labelled "Demo data"; the
 * real answer replaces it when it lands. Loaded on demand: most visits never
 * need it.
 */
let loaded: Promise<Map<string, Presentation>> | null = null;

export function loadDemoAnswers(): Promise<Map<string, Presentation>> {
  loaded ??= import("./demo-answers.json").then(
    ({ default: data }) =>
      new Map(
        data.stories.map((story) => [
          story.question,
          readPresentation(story.presentation as unknown as Record<string, unknown>),
        ]),
      ),
  );
  return loaded;
}
