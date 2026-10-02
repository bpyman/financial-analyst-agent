"use client";

import { catchError } from "next/error";
import { Callout } from "./ui";

/**
 * One answer's error boundary: an answer the window cannot draw (a stored
 * shape it does not expect) shows this card, and the rest of the thread stays.
 */
export const AnswerBoundary = catchError(() => (
  <Callout kind="warning">This answer couldn&apos;t be shown. The rest of the conversation is unaffected.</Callout>
));
