import { describe, expect, it } from "vitest";

async function readWorkspaceCss(): Promise<string> {
  const fsSpec = "node:fs";
  const pathSpec = "node:path";
  const [{ readFileSync }, { resolve }] = await Promise.all([
    import(fsSpec) as Promise<{
      readFileSync: (path: string, encoding: string) => string;
    }>,
    import(pathSpec) as Promise<{
      resolve: (...parts: string[]) => string;
    }>,
  ]);
  const cwd =
    (globalThis as { process?: { cwd: () => string } }).process?.cwd() ?? "";
  return readFileSync(resolve(cwd, "src/styles.css"), "utf8");
}

describe("workspace scroll containment", () => {
  it("does not let html overflow-x create a document vertical scroller", async () => {
    const css = await readWorkspaceCss();
    expect(css).toMatch(/html\s*\{[^}]*overflow:\s*hidden;/);
    expect(css).not.toMatch(/html\s*\{[^}]*overflow-x\s*:/);
  });

  it("contains Human Review scrolling inside the main workspace", async () => {
    const css = await readWorkspaceCss();
    expect(css).toMatch(/\.main-content\s*\{[^}]*overflow-y:\s*auto;/);
    expect(css).toMatch(
      /\.main-content\s*\{[^}]*overscroll-behavior:\s*contain;/,
    );
  });
});
