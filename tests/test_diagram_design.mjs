import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import puppeteer from "puppeteer";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const harnessSource = resolve(projectRoot, "harnesses/diagram-design/slides.md");
const workRoot = resolve(projectRoot, "work");
await mkdir(workRoot, { recursive: true });
const harnessOutputRoot = await mkdtemp(resolve(workRoot, "diagram-design-"));
const harnessOutput = resolve(harnessOutputRoot, "index.html");
const screenshotPath = process.env.DIAGRAM_DESIGN_SCREENSHOT;
const pythonExecutable = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const execFileAsync = promisify(execFile);
const executablePath = [
  process.env.PUPPETEER_EXECUTABLE_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].find(candidate => candidate && existsSync(candidate));
let browser = null;

try {
  await execFileAsync(
    pythonExecutable,
    [resolve(projectRoot, "build_slides.py"), harnessSource, "-o", harnessOutput, "--strict"],
    { cwd: projectRoot, windowsHide: true }
  );
  browser = await puppeteer.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(harnessOutput).href, { waitUntil: "load" });

  const delivery = await page.evaluate(() => {
    const figure = document.querySelector('[data-diagram-engine="diagram-design"]');
    const svg = figure?.querySelector("svg");
    const title = svg?.querySelector(":scope > title");
    const description = svg?.querySelector(":scope > desc");
    const labels = [...(svg?.querySelectorAll("text") || [])];
    const bounds = figure?.getBoundingClientRect();
    return {
      figureFound: Boolean(figure),
      svgFound: Boolean(svg),
      viewBox: svg?.getAttribute("viewBox"),
      role: svg?.getAttribute("role"),
      labelledBy: svg?.getAttribute("aria-labelledby"),
      title: title?.textContent,
      description: description?.textContent,
      titleResolves: Boolean(title?.id && svg?.getAttribute("aria-labelledby")?.includes(title.id)),
      descriptionResolves: Boolean(description?.id && svg?.getAttribute("aria-labelledby")?.includes(description.id)),
      minimumFontSize: Math.min(...labels.map(label => Number.parseFloat(getComputedStyle(label).fontSize))),
      bounds: bounds ? { width: bounds.width, height: bounds.height } : null,
      mermaidRuntime: typeof window.mermaid !== "undefined" || document.documentElement.innerHTML.includes("mermaid.run"),
      remoteResources: performance.getEntriesByType("resource")
        .map(entry => entry.name)
        .filter(name => /^https?:/i.test(name)),
    };
  });

  assert.equal(delivery.figureFound, true);
  assert.equal(delivery.svgFound, true);
  assert.equal(delivery.viewBox, "0 0 1840 800");
  assert.equal(delivery.role, "img");
  assert(delivery.labelledBy);
  assert.equal(delivery.title, "Mermaid 编辑式重绘链路");
  assert(delivery.description?.includes("Mermaid 语义源"));
  assert.equal(delivery.titleResolves, true);
  assert.equal(delivery.descriptionResolves, true);
  assert(delivery.minimumFontSize >= 28, `minimum rendered font should be 28px: ${delivery.minimumFontSize}`);
  assert(delivery.bounds?.width > 1700 && delivery.bounds?.height > 700, `diagram should own the stage: ${JSON.stringify(delivery.bounds)}`);
  assert.equal(delivery.mermaidRuntime, false);
  assert.deepEqual(delivery.remoteResources, []);

  if (screenshotPath) {
    await mkdir(dirname(resolve(screenshotPath)), { recursive: true });
    await page.screenshot({ path: resolve(screenshotPath), fullPage: true });
  }

  console.log("Diagram Design browser test passed.");
} finally {
  if (browser) await browser.close();
  await rm(harnessOutputRoot, { recursive: true, force: true });
}
