import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import puppeteer from "puppeteer";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const harnessSource = resolve(projectRoot, "harnesses/citations/slides.md");
const workRoot = resolve(projectRoot, "work");
await mkdir(workRoot, { recursive: true });
const harnessOutputRoot = await mkdtemp(resolve(workRoot, "citations-"));
const harnessOutput = resolve(harnessOutputRoot, "index.html");
const screenshotPath = process.env.CITATIONS_SCREENSHOT;
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

  const refs = await page.$$(".slide.active .citation-ref");
  assert.equal(refs.length, 2, "harness should render two citations");
  assert.deepEqual(
    await page.$$eval(".slide.active .citation-ref", nodes => nodes.map(node => node.textContent)),
    ["1", "1"],
    "repeated IDs should reuse the first-use number"
  );

  await refs[0].hover();
  await page.waitForFunction(() => document.querySelector(".citation-tooltip")?.dataset.open === "true");
  const tooltip = await page.evaluate(() => {
    const node = document.querySelector(".citation-tooltip");
    const rect = node.getBoundingClientRect();
    return {
      role: node.getAttribute("role"),
      text: node.querySelector(".citation-tooltip-text").textContent,
      url: node.querySelector(".citation-tooltip-link").textContent,
      href: node.querySelector(".citation-tooltip-link").href,
      withinViewport: rect.left >= 0 && rect.right <= innerWidth && rect.top >= 0 && rect.bottom <= innerHeight,
    };
  });
  assert.equal(tooltip.role, "tooltip");
  assert.match(tooltip.text, /Kimi/);
  assert.match(tooltip.url, /www\.kimi\.ai\/zh-hant\/resources\/best-ai-agent-frameworks/);
  assert.equal(tooltip.href, "https://www.kimi.ai/zh-hant/resources/best-ai-agent-frameworks");
  assert.equal(tooltip.withinViewport, true);

  await refs[0].focus();
  assert.equal(await refs[0].evaluate(node => node.getAttribute("aria-expanded")), "true");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.querySelector(".citation-tooltip")?.dataset.open === "false");
  assert.equal(await refs[0].evaluate(node => node.getAttribute("aria-expanded")), "false");

  const flipped = await page.evaluate(() => {
    const clone = document.querySelector(".citation-ref").cloneNode(true);
    Object.assign(clone.style, {position: "fixed", right: "4px", bottom: "2px", zIndex: "31000"});
    document.body.appendChild(clone);
    window.__SLIDE_CITATIONS__.show(clone);
    const anchor = clone.getBoundingClientRect();
    const tip = document.querySelector(".citation-tooltip").getBoundingClientRect();
    const result = tip.bottom <= innerHeight && tip.top < anchor.top && tip.right <= innerWidth;
    window.__SLIDE_CITATIONS__.hide();
    clone.remove();
    return result;
  });
  assert.equal(flipped, true, "tooltip should flip above and stay inside the viewport near the bottom edge");

  if (screenshotPath) {
    await refs[0].evaluate(node => window.__SLIDE_CITATIONS__.show(node));
    await page.waitForFunction(() => document.querySelector(".citation-tooltip")?.dataset.open === "true");
    await mkdir(dirname(resolve(screenshotPath)), { recursive: true });
    await page.screenshot({ path: resolve(screenshotPath), fullPage: true });
  }

  console.log("Citations browser test passed.");
} finally {
  if (browser) await browser.close();
  await rm(harnessOutputRoot, { recursive: true, force: true });
}
