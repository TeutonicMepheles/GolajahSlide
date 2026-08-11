import { access, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";
import puppeteer from "puppeteer";

const args = process.argv.slice(2);
const valueFor = (name) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : null;
};
const input = valueFor("--input");
const output = valueFor("--output");
const rawPadding = valueFor("--padding") ?? "32";
if (!input || !output) {
  console.error("Usage: node tools/render_excalidraw.mjs --input scene.excalidraw --output scene.svg [--padding 32]");
  process.exit(2);
}

const exportPadding = Number(rawPadding);
if (!Number.isFinite(exportPadding) || exportPadding < 0) {
  console.error("--padding must be a non-negative number");
  process.exit(2);
}

const existingBrowser = async () => {
  const configured = process.env.DIAGRAM_CHROME || process.env.PUPPETEER_EXECUTABLE_PATH;
  const candidates = [
    configured,
    process.platform === "win32" ? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" : null,
    process.platform === "win32" ? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" : null,
    process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : null,
    process.platform === "linux" ? "/usr/bin/google-chrome" : null,
    process.platform === "linux" ? "/usr/bin/chromium" : null,
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Continue to Puppeteer's managed browser.
    }
  }
  try {
    const managed = puppeteer.executablePath();
    await access(managed);
    return managed;
  } catch {
    throw new Error("No Chrome/Chromium executable found; set DIAGRAM_CHROME to its absolute path");
  }
};

const temporary = await mkdtemp(path.join(os.tmpdir(), "golajah-excalidraw-"));
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
let browser;
try {
  const bundle = path.join(temporary, "excalidraw-exporter.js");
  await build({
    entryPoints: [path.join(scriptDirectory, "excalidraw_export_entry.mjs")],
    outfile: bundle,
    bundle: true,
    format: "iife",
    platform: "browser",
    target: ["chrome120"],
    loader: {
      ".woff": "dataurl",
      ".woff2": "dataurl",
      ".ttf": "dataurl",
      ".png": "dataurl",
      ".svg": "dataurl",
    },
    logLevel: "silent",
  });

  const scene = JSON.parse(await readFile(path.resolve(input), "utf8"));
  browser = await puppeteer.launch({
    executablePath: await existingBrowser(),
    headless: true,
    args: ["--disable-dev-shm-usage"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.setContent("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>");
  await page.addScriptTag({ content: await readFile(bundle, "utf8") });
  await page.waitForFunction(() => globalThis.excalidrawExporterReady === true);
  const result = await page.evaluate(
    async ({ scenePayload, padding }) => globalThis.renderExcalidrawScene(scenePayload, { exportPadding: padding }),
    { scenePayload: scene, padding: exportPadding },
  );
  await writeFile(path.resolve(output), result.svg + "\n", "utf8");
  process.stdout.write(JSON.stringify(result.metrics) + "\n");
} catch (error) {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
} finally {
  if (browser) {
    await browser.close();
  }
  await rm(temporary, { recursive: true, force: true });
}
