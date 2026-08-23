import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import puppeteer from "puppeteer";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const harnessSource = resolve(projectRoot, "harnesses/media-playback/slides.md");
const workRoot = resolve(projectRoot, "work");
await mkdir(workRoot, { recursive: true });
const outputRoot = await mkdtemp(resolve(workRoot, "media-playback-"));
const output = resolve(outputRoot, "index.html");
const pythonExecutable = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const execFileAsync = promisify(execFile);
const executablePath = [
  process.env.PUPPETEER_EXECUTABLE_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].find(candidate => candidate && existsSync(candidate));
let browser = null;

try {
  await execFileAsync(pythonExecutable, [resolve(projectRoot, "build_slides.py"), harnessSource, "-o", output, "--strict"], {cwd: projectRoot, windowsHide: true});
  browser = await puppeteer.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage();
  await page.setViewport({width: 1920, height: 1080, deviceScaleFactor: 1});
  await page.goto(pathToFileURL(output).href, {waitUntil: "load"});

  assert.equal(await page.$$eval("[data-slide-video]", nodes => nodes.length), 3);
  assert.equal(await page.$eval("[data-slide-video]", node => node.hasAttribute("controls") && node.hasAttribute("playsinline")), true);
  assert.match(await page.$eval("[data-slide-video] source", node => node.getAttribute("src")), /^data:video\/mp4;base64,/);
  assert.match(await page.$eval("[data-slide-video]", node => node.getAttribute("poster")), /^data:image\/png;base64,/);

  await page.$eval("[data-slide-video]", async video => {
    video.muted = true;
    await video.play();
  });
  await page.waitForFunction(() => document.querySelector("[data-slide-video]")?.currentTime > 0.05);
  assert.equal(await page.$eval("[data-slide-video]", video => video.paused), false);
  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(1, false));
  await page.waitForFunction(() => document.querySelector("[data-slide-video]")?.paused === true);
  assert.equal(await page.$eval("[data-slide-video]", video => video.paused), true);
  assert.equal(await page.$eval("[data-video-autoplay]", video => (
    video.autoplay && video.loop && video.muted && !video.controls && video.hasAttribute("playsinline")
  )), true);
  await page.waitForFunction(() => document.querySelector("[data-video-autoplay]")?.currentTime > 0.05);
  assert.equal(await page.$eval("[data-video-autoplay]", video => video.paused), false);
  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(2, false));
  const tabbedVideo = "[data-slide-id='tabbed-autoplay-video'] [data-media-panel='1'] video";
  await page.waitForFunction(selector => document.querySelector(selector)?.paused === true, {}, tabbedVideo);
  await page.click("[data-slide-id='tabbed-autoplay-video'] [data-media-target='1']");
  await page.waitForFunction(selector => {
    const video = document.querySelector(selector);
    return video && !video.paused && video.currentTime > 0.05;
  }, {}, tabbedVideo);
  await page.click("[data-slide-id='tabbed-autoplay-video'] [data-media-target='0']");
  await page.waitForFunction(selector => document.querySelector(selector)?.paused === true, {}, tabbedVideo);
  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(3, false));
  await page.waitForFunction(() => document.querySelector("[data-video-autoplay]")?.paused === true);
  assert.equal(await page.$eval("[data-video-autoplay]", video => video.paused), true);
  assert.equal(await page.evaluate(() => Boolean(window.__SLIDE_MEDIA_PLAYBACK__)), true);

  console.log("Media playback browser test passed.");
} finally {
  if (browser) await browser.close();
  await rm(outputRoot, {recursive: true, force: true});
}
