import { describe, expect, it } from "vitest";
import { findFfmpeg, gifArgs, mp4Args } from "./portfolio-media";

describe("findFfmpeg", () => {
  it("prefers $FFMPEG when it runs", () => {
    const tried: string[] = [];
    const found = findFfmpeg({ FFMPEG: "/opt/ffmpeg" }, (cmd) => {
      tried.push(cmd);
      return true;
    });
    expect(found).toBe("/opt/ffmpeg");
    expect(tried).toEqual(["/opt/ffmpeg"]);
  });

  it("falls back to ffmpeg on PATH", () => {
    expect(findFfmpeg({}, (cmd) => cmd === "ffmpeg")).toBe("ffmpeg");
  });

  it("says how to fix it when $FFMPEG does not run", () => {
    expect(() => findFfmpeg({ FFMPEG: "/nope" }, () => false)).toThrow(/FFMPEG=\/nope does not run/);
  });

  it("says how to fix it when there is no ffmpeg at all", () => {
    expect(() => findFfmpeg({}, () => false)).toThrow(/install ffmpeg or set FFMPEG/);
  });
});

describe("mp4Args", () => {
  it("encodes H.264 that plays inline on GitHub, trimmed to the walkthrough", () => {
    const args = mp4Args("in.webm", "out.mp4", { startAt: 1.25 });
    expect(args.slice(0, 5)).toEqual(["-y", "-ss", "1.250", "-i", "in.webm"]);
    expect(args).toContain("libx264");
    expect(args.join(" ")).toContain("-pix_fmt yuv420p");
    expect(args.join(" ")).toContain("-movflags +faststart");
    expect(args).toContain("-an");
    expect(args.at(-1)).toBe("out.mp4");
  });
});

describe("gifArgs", () => {
  it("builds one palette for the whole clip and loops forever", () => {
    const args = gifArgs("in.webm", "out.gif", { startAt: 0, fps: 10, width: 960 });
    const filter = args[args.indexOf("-vf") + 1];
    expect(filter).toMatch(/^fps=10,scale=960:-1:flags=lanczos,/);
    expect(filter).toContain("palettegen");
    expect(filter).toContain("paletteuse");
    expect(args.join(" ")).toContain("-loop 0");
    expect(args.at(-1)).toBe("out.gif");
  });
});
