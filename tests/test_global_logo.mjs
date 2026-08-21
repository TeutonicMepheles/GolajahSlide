import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import puppeteer from "puppeteer";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const harnessSource = resolve(projectRoot, "harnesses/global-logo/slides.md");
const workRoot = resolve(projectRoot, "work");
await mkdir(workRoot, { recursive: true });
const harnessOutputRoot = await mkdtemp(resolve(workRoot, "global-logo-"));
const harnessOutput = resolve(harnessOutputRoot, "index.html");
const exampleUrl = pathToFileURL(harnessOutput).href;
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
  await page.goto(exampleUrl, { waitUntil: "load" });

  assert.equal(await page.$$eval("[data-global-logo]", nodes => nodes.length), 2);
  assert.equal(await page.$$eval("[data-global-logo]", nodes => nodes.every(node => node.hidden)), true);

  await page.keyboard.press("e");
  await page.waitForFunction(() => document.body.classList.contains("editor-open"));
  await page.$eval("#editorLogoEnabled", node => node.scrollIntoView({block: "center"}));
  await page.$eval("#editorLogoEnabled", node => node.click());
  assert.equal(await page.$eval("#editorLogoEnabled", node => node.getAttribute("aria-pressed")), "true");
  assert.equal(await page.$$eval("[data-global-logo]", nodes => nodes.every(node => !node.hidden && !node.classList.contains("has-image"))), true);

  const resizeHandle = await page.$(".slide.active .global-logo-resize-handle");
  const handleBox = await resizeHandle.boundingBox();
  assert(handleBox, "editor mode should expose a global logo resize handle");
  await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(handleBox.x - 40, handleBox.y + handleBox.height / 2 + 16, {steps: 4});
  await page.mouse.up();
  const resized = await page.evaluate(() => window.__SLIDE_GLOBAL_LOGO__.config());
  assert(resized.width > 190, `dragging left should increase width: ${resized.width}`);
  assert(resized.height > 72, `dragging down should increase height: ${resized.height}`);
  assert.equal(await page.$$eval("[data-global-logo]", nodes => new Set(nodes.map(node => getComputedStyle(node).width)).size), 1);

  const alignment = await page.evaluate(() => {
    const header = document.querySelector(".slide.active .slide-header").getBoundingClientRect();
    const logo = document.querySelector(".slide.active [data-global-logo]").getBoundingClientRect();
    return Math.abs((header.top + header.height / 2) - (logo.top + logo.height / 2));
  });
  assert(alignment < 1, `logo should vertically align with the title region, delta=${alignment}`);

  await page.evaluate(() => {
    const bytes = Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="), character => character.charCodeAt(0));
    const file = new File([bytes], "brand.png", {type: "image/png"});
    const transfer = new DataTransfer();
    transfer.items.add(file);
    const input = document.getElementById("editorLogoFile");
    Object.defineProperty(input, "files", {value: transfer.files, configurable: true});
    input.dispatchEvent(new Event("change", {bubbles: true}));
  });
  await page.waitForFunction(() => document.querySelector("[data-global-logo]")?.classList.contains("has-image"));

  const exported = await page.evaluate(() => window.__SLIDE_LAYOUT_EDITOR__.exportPayload().branding.logo);
  assert.equal(exported.enabled, true);
  assert.equal(exported.width, resized.width);
  assert.equal(exported.height, resized.height);
  assert.match(exported.src, /^data:image\/png;base64,/);
  assert.equal(await page.$$eval("[data-global-logo] img", nodes => nodes.every(node => !node.hidden && node.src.startsWith("data:image/png;base64,"))), true);

  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(1, false));
  assert.equal(await page.$eval(".slide.active [data-global-logo]", node => node.classList.contains("has-image")), true);

  await page.reload({waitUntil: "load"});
  assert.equal(await page.$eval("#editorLogoEnabled", node => node.getAttribute("aria-pressed")), "true");
  assert.equal(await page.$eval(".slide.active [data-global-logo] img", node => node.src.startsWith("data:image/png;base64,")), true);

  const invalidMessage = await page.evaluate(async () => {
    try {
      await window.__SLIDE_GLOBAL_LOGO__.sourceFromFile(new File(["bad"], "logo.svg", {type: "image/svg+xml"}));
      return "";
    } catch (error) {
      return error.message;
    }
  });
  assert.match(invalidMessage, /PNG、JPEG 或 WebP/);

  console.log("Global logo browser test passed.");
} finally {
  if (browser) await browser.close();
  await rm(harnessOutputRoot, {recursive: true, force: true});
}
