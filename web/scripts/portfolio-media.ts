/**
 * ffmpeg commands that turn the capture script's recording into the README's
 * walkthrough (`capture-portfolio.ts`). Pure, so the unit tests pin them.
 */

/** The ffmpeg to run: `$FFMPEG` if set, else `ffmpeg` on PATH. Throws a fix-it message otherwise. */
export function findFfmpeg(
  env: Record<string, string | undefined>,
  runs: (command: string) => boolean,
): string {
  const chosen = env.FFMPEG?.trim();
  if (chosen) {
    if (runs(chosen)) return chosen;
    throw new Error(`FFMPEG=${chosen} does not run. Point FFMPEG at an ffmpeg binary, or unset it.`);
  }
  if (runs("ffmpeg")) return "ffmpeg";
  throw new Error(
    "ffmpeg was not found on PATH. To convert the recording, install ffmpeg or set FFMPEG " +
      "to an ffmpeg binary (for example `uvx --from imageio-ffmpeg python -c " +
      "\"import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())\"` prints one).",
  );
}

export interface ClipOptions {
  /** Seconds to drop from the start of the recording (the page loading). */
  startAt: number;
}

export interface GifOptions extends ClipOptions {
  fps: number;
  width: number;
}

function input(source: string, { startAt }: ClipOptions): string[] {
  return ["-y", "-ss", startAt.toFixed(3), "-i", source];
}

/** H.264 in yuv420p with the index up front, so GitHub and browsers play it inline. */
export function mp4Args(source: string, target: string, options: ClipOptions): string[] {
  return [
    ...input(source, options),
    "-vf",
    "scale=trunc(iw/2)*2:trunc(ih/2)*2",
    "-c:v",
    "libx264",
    "-preset",
    "slow",
    "-crf",
    "24",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
    "-an",
    target,
  ];
}

/**
 * One 64-colour palette for the whole clip, no dithering (the window is flat colour),
 * only changed rectangles redrawn, looping forever. Keeps a 25s walkthrough near 4 MB.
 */
export function gifArgs(source: string, target: string, options: GifOptions): string[] {
  const filter =
    `fps=${options.fps},scale=${options.width}:-1:flags=lanczos,split[a][b];` +
    "[a]palettegen=max_colors=64:stats_mode=diff[p];" +
    "[b][p]paletteuse=dither=none:diff_mode=rectangle";
  return [...input(source, options), "-vf", filter, "-loop", "0", target];
}
