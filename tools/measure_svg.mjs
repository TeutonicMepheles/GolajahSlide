import { access, readFile } from "node:fs/promises";
import path from "node:path";

import puppeteer from "puppeteer";

const args = process.argv.slice(2);
const valueFor = (name) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : null;
};
const input = valueFor("--input");
const configuredBrowser = valueFor("--chrome") || process.env.DIAGRAM_CHROME || process.env.PUPPETEER_EXECUTABLE_PATH;
if (!input) {
  console.error("Usage: node tools/measure_svg.mjs --input diagram.svg [--chrome /path/to/chrome]");
  process.exit(2);
}

const browserCandidates = [
  configuredBrowser,
  process.platform === "win32" ? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" : null,
  process.platform === "win32" ? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" : null,
  process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : null,
  process.platform === "linux" ? "/usr/bin/google-chrome" : null,
  process.platform === "linux" ? "/usr/bin/chromium" : null,
].filter(Boolean);
let executablePath = null;
for (const candidate of browserCandidates) {
  try {
    await access(candidate);
    executablePath = candidate;
    break;
  } catch {
    // Try the next browser.
  }
}
if (!executablePath) {
  try {
    const managed = puppeteer.executablePath();
    await access(managed);
    executablePath = managed;
  } catch {
    console.error("No Chrome/Chromium executable found");
    process.exit(2);
  }
}

const source = await readFile(path.resolve(input), "utf8");
let browser;
try {
  browser = await puppeteer.launch({ executablePath, headless: true, args: ["--disable-dev-shm-usage"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 2400, height: 1600, deviceScaleFactor: 1 });
  await page.setContent(`<!doctype html><style>html,body{margin:0;padding:0}</style>${source}`);
  await page.evaluate(() => document.fonts?.ready);
  const result = await page.evaluate(() => {
    const svg = document.querySelector("svg");
    if (!svg?.viewBox?.baseVal?.width || !svg.viewBox.baseVal.height) {
      throw new Error("SVG is missing a valid viewBox");
    }
    const { width, height } = svg.viewBox.baseVal;
    svg.setAttribute("width", String(width));
    svg.setAttribute("height", String(height));
    svg.style.width = `${width}px`;
    svg.style.height = `${height}px`;
    svg.style.maxWidth = "none";
    svg.style.maxHeight = "none";
    const rootRect = svg.getBoundingClientRect();
    const candidates = [...svg.querySelectorAll("path,rect,circle,ellipse,polygon,polyline,line,text,image,use")]
      .filter((element) => !element.closest("defs,marker,clipPath,mask,pattern"));
    const boxes = [];
    for (const element of candidates) {
      const style = getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) continue;
      if (style.fill === "none" && style.stroke === "none") continue;
      const box = element.getBoundingClientRect();
      if (box.width <= 0 && box.height <= 0) continue;
      if (box.width >= rootRect.width * 0.98 && box.height >= rootRect.height * 0.98) continue;
      boxes.push(box);
    }
    if (!boxes.length) throw new Error("SVG has no measurable visible graphics");
    const left = Math.min(...boxes.map((box) => box.left)) - rootRect.left;
    const top = Math.min(...boxes.map((box) => box.top)) - rootRect.top;
    const right = rootRect.right - Math.max(...boxes.map((box) => box.right));
    const bottom = rootRect.bottom - Math.max(...boxes.map((box) => box.bottom));
    return {
      minimumSafeMargin: Math.max(0, Math.min(left, top, right, bottom)),
      margins: { left, top, right, bottom },
      visibleElementCount: boxes.length,
    };
  });
  process.stdout.write(JSON.stringify(result) + "\n");
} catch (error) {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
}
