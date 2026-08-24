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

  const standaloneManual = "[data-slide-id='video'] [data-slide-video]";
  const standaloneAutoplay = "[data-slide-id='after-video'] [data-slide-video]";
  const tabbedShell = "[data-slide-id='tabbed-autoplay-video'] [data-media-panel='1'][data-slide-video-shell]";
  const tabbedVideo = `${tabbedShell} video`;
  const gridVideos = "[data-slide-id='grid-manual-videos'] [data-slide-video]";

  assert.equal(await page.$$eval("[data-slide-video]", nodes => nodes.length), 5);
  assert.equal(await page.$$eval("[data-slide-video-shell]", nodes => nodes.length), 5);
  assert.equal(await page.$$eval("[data-video-fullscreen]", nodes => nodes.length), 5);
  assert.equal(await page.$eval(standaloneManual, node => node.hasAttribute("controls") && node.hasAttribute("playsinline")), true);
  assert.match(await page.$eval(`${standaloneManual} source`, node => node.getAttribute("src")), /^data:video\/mp4;base64,/);
  assert.match(await page.$eval(standaloneManual, node => node.getAttribute("poster")), /^data:image\/png;base64,/);
  const fullscreenControls = await page.$$eval("[data-slide-video-shell]", shells => shells.map(shell => {
    const buttons = [...shell.querySelectorAll("[data-video-fullscreen]")];
    return {
      count: buttons.length,
      type: buttons[0]?.getAttribute("type"),
      label: buttons[0]?.getAttribute("aria-label"),
      pressed: buttons[0]?.getAttribute("aria-pressed"),
    };
  }));
  assert(fullscreenControls.every(control => (
    control.count === 1 && control.type === "button" && control.label?.startsWith("全屏播放") && control.pressed === "false"
  )), `every video should expose one accessible fullscreen control: ${JSON.stringify(fullscreenControls)}`);
  assert.equal(await page.$$eval(gridVideos, nodes => nodes.length), 2);
  assert.equal(await page.$$eval("[data-slide-id='grid-manual-videos'] [data-video-fullscreen]", nodes => nodes.length), 2);

  await page.evaluate(() => {
    window.__SLIDE_MEDIA_PLAYBACK__.reconcile(document);
    window.__SLIDE_MEDIA_PLAYBACK__.reconcile(document);
  });
  assert.equal(await page.$$eval("[data-video-fullscreen]", nodes => nodes.length), 5, "reconcile should be idempotent");

  await page.$eval(standaloneManual, async video => {
    video.muted = true;
    await video.play();
  });
  await page.waitForFunction(selector => document.querySelector(selector)?.currentTime > 0.05, {}, standaloneManual);
  assert.equal(await page.$eval(standaloneManual, video => video.paused), false);
  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(1, false));
  await page.waitForFunction(selector => document.querySelector(selector)?.paused === true, {}, standaloneManual);
  assert.equal(await page.$eval(standaloneManual, video => video.paused), true);
  assert.equal(await page.$eval(standaloneAutoplay, video => (
    video.autoplay && video.loop && video.muted && !video.controls && video.hasAttribute("playsinline")
  )), true);
  await page.waitForFunction(selector => document.querySelector(selector)?.currentTime > 0.05, {}, standaloneAutoplay);
  assert.equal(await page.$eval(standaloneAutoplay, video => video.paused), false);
  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(2, false));
  await page.waitForFunction(selector => document.querySelector(selector)?.paused === true, {}, tabbedVideo);
  assert.equal(
    await page.$eval(`${tabbedShell} [data-video-fullscreen]`, button => getComputedStyle(button).visibility),
    "hidden",
    "the fullscreen control in an inactive Gallery tab should not be exposed"
  );
  await page.click("[data-slide-id='tabbed-autoplay-video'] [data-media-target='1']");
  await page.waitForFunction(selector => {
    const video = document.querySelector(selector);
    return video && !video.paused && video.currentTime > 0.05;
  }, {}, tabbedVideo);
  await page.click("[data-slide-id='tabbed-autoplay-video'] [data-media-target='0']");
  await page.waitForFunction(selector => document.querySelector(selector)?.paused === true, {}, tabbedVideo);

  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(4, false));
  await page.waitForFunction(selector => document.querySelector(selector)?.paused === true, {}, standaloneAutoplay);
  assert.equal(await page.$eval(standaloneAutoplay, video => video.paused), true);

  await page.evaluate(() => {
    const mock = {element: null, requests: 0, exits: 0};
    window.__mediaFullscreenMock = mock;
    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      get: () => mock.element,
    });
    document.exitFullscreen = async () => {
      mock.exits += 1;
      mock.element = null;
      document.dispatchEvent(new Event("fullscreenchange"));
    };
    const shell = document.querySelector("[data-slide-id='video'] [data-slide-video-shell]");
    shell.requestFullscreen = async () => {
      mock.requests += 1;
      mock.element = shell;
    };
    window.__SLIDE_PRESENTATION__.show(0, false);
  });
  const standaloneFullscreen = "[data-slide-id='video'] [data-video-fullscreen]";
  await page.focus(standaloneFullscreen);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => (
    window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen &&
    window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode?.startsWith("native") &&
    window.__SLIDE_MEDIA_PLAYBACK__.fullscreenShell === document.querySelector("[data-slide-id='video'] [data-slide-video-shell]")
  ));
  assert.equal(await page.$eval(standaloneFullscreen, button => button.getAttribute("aria-pressed")), "true");
  assert.equal(await page.$eval(standaloneFullscreen, button => button.getAttribute("aria-label")?.startsWith("退出全屏")), true);
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains("video-fullscreen-close")), true, "native shell fullscreen should focus its visible exit control");
  assert.equal(await page.evaluate(() => window.__mediaFullscreenMock.requests), 1);

  await page.evaluate(() => {
    window.__mediaFullscreenMock.element = null;
    document.dispatchEvent(new Event("fullscreenchange"));
  });
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);
  assert.equal(await page.$eval(standaloneFullscreen, button => button.getAttribute("aria-pressed")), "false");
  assert.equal(await page.$eval(standaloneFullscreen, button => button.getAttribute("aria-label")?.startsWith("全屏播放")), true);

  await page.click(standaloneFullscreen);
  await page.waitForFunction(() => window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode?.startsWith("native"));
  await page.click("[data-slide-id='video'] .video-fullscreen-close");
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);
  assert.equal(await page.evaluate(() => window.__mediaFullscreenMock.exits), 1, "the active fullscreen button should call exitFullscreen");

  await page.click(standaloneFullscreen);
  await page.waitForFunction(() => window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode === "native-shell");
  await page.evaluate(() => {
    document.exitFullscreen = async () => {
      window.__mediaFullscreenMock.exits += 1;
      throw new Error("simulated native exit refusal");
    };
  });
  await page.click("[data-slide-id='video'] .video-fullscreen-close");
  await new Promise(resolve => setTimeout(resolve, 80));
  assert.equal(await page.evaluate(() => window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen), true, "a failed native exit must keep navigation blocked and local fullscreen state intact");
  await page.evaluate(() => {
    document.exitFullscreen = async () => {
      window.__mediaFullscreenMock.exits += 1;
      window.__mediaFullscreenMock.element = null;
      document.dispatchEvent(new Event("fullscreenchange"));
    };
    window.__SLIDE_MEDIA_PLAYBACK__.exitFullscreen();
  });
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);

  await page.evaluate(() => {
    const shell = document.querySelector("[data-slide-id='video'] [data-slide-video-shell]");
    const video = shell.querySelector("video");
    shell.requestFullscreen = undefined;
    window.__mediaWebkitFullscreenMock = {entries: 0, exits: 0, legacyEntries: 0};
    shell.webkitRequestFullscreen = () => { window.__mediaWebkitFullscreenMock.legacyEntries += 1; };
    Object.defineProperty(video, "webkitSupportsFullscreen", {configurable: true, value: true});
    Object.defineProperty(video, "webkitEnterFullscreen", {
      configurable: true,
      value: () => { window.__mediaWebkitFullscreenMock.entries += 1; },
    });
    Object.defineProperty(video, "webkitExitFullscreen", {
      configurable: true,
      value: () => {
        window.__mediaWebkitFullscreenMock.exits += 1;
        video.dispatchEvent(new Event("webkitendfullscreen"));
      },
    });
  });
  await page.click(standaloneFullscreen);
  await page.waitForFunction(() => window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode === "webkit-video");
  assert.deepEqual(await page.evaluate(() => window.__mediaWebkitFullscreenMock), {entries: 1, exits: 0, legacyEntries: 0});
  await page.evaluate(() => window.__SLIDE_MEDIA_PLAYBACK__.exitFullscreen());
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);
  assert.deepEqual(await page.evaluate(() => window.__mediaWebkitFullscreenMock), {entries: 1, exits: 1, legacyEntries: 0});

  await page.evaluate(() => {
    window.__SLIDE_PRESENTATION__.show(1, false);
    const shell = document.querySelector("[data-slide-id='after-video'] [data-slide-video-shell]");
    shell.requestFullscreen = () => new Promise(() => {});
    window.__SLIDE_MEDIA_PLAYBACK__.fullscreenTimeoutMs = 60;
  });
  await page.click("[data-slide-id='after-video'] [data-video-fullscreen]");
  await page.waitForFunction(() => Boolean(window.__SLIDE_MEDIA_PLAYBACK__.pendingRecord));
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);
  assert.equal(await page.evaluate(() => document.activeElement?.matches("[data-slide-id='after-video'] [data-video-fullscreen]")), true, "Escape should cancel pending fullscreen and restore the trigger focus");
  await page.click("[data-slide-id='after-video'] [data-video-fullscreen]");
  await page.waitForFunction(() => Boolean(window.__SLIDE_MEDIA_PLAYBACK__.pendingRecord));
  await page.evaluate(() => window.__SLIDE_LAYOUT_EDITOR__.setActive(true));
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);
  await new Promise(resolve => setTimeout(resolve, 120));
  assert.deepEqual(await page.evaluate(() => {
    const runtime = window.__SLIDE_MEDIA_PLAYBACK__;
    const shell = document.querySelector("[data-slide-id='after-video'] [data-slide-video-shell]");
    return {
      pending: Boolean(runtime.pendingRecord),
      fullscreen: Boolean(runtime.fullscreenRecord),
      overlayHidden: runtime.overlay.hidden,
      shellInSlide: Boolean(shell?.closest(".slide")),
      controls: shell?.querySelector("video")?.controls,
    };
  }), {pending: false, fullscreen: false, overlayHidden: true, shellInSlide: true, controls: false});
  const lateNativeExitCount = await page.evaluate(() => window.__mediaFullscreenMock.exits);
  await page.evaluate(() => {
    window.__mediaFullscreenMock.element = document.querySelector("[data-slide-id='after-video'] [data-slide-video-shell]");
    document.dispatchEvent(new Event("fullscreenchange"));
  });
  await page.waitForFunction(count => window.__mediaFullscreenMock.exits === count + 1, {}, lateNativeExitCount);
  assert.equal(await page.evaluate(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen && window.__mediaFullscreenMock.element === null), true, "late native success after pending cancellation should be exited immediately");
  await page.evaluate(() => {
    window.__SLIDE_LAYOUT_EDITOR__.setActive(false);
    window.__SLIDE_MEDIA_PLAYBACK__.fullscreenTimeoutMs = 900;
    window.__SLIDE_PRESENTATION__.show(0, false);
  });

  const fallbackState = await page.evaluate(async () => {
    const shell = document.querySelector("[data-slide-id='video'] [data-slide-video-shell]");
    const video = shell.querySelector("video");
    shell.requestFullscreen = () => new Promise(() => {});
    window.__mediaFallbackOrigin = {parent: shell.parentNode, next: shell.nextSibling};
    const preservedBackground = document.querySelector(".deck-status");
    preservedBackground.setAttribute("inert", "");
    preservedBackground.setAttribute("aria-hidden", "false");
    video.muted = true;
    await video.play();
    await new Promise(resolve => setTimeout(resolve, 100));
    return {currentTime: video.currentTime, slideIndex: window.__SLIDE_PRESENTATION__.current};
  });
  await page.click(standaloneFullscreen);
  await page.waitForFunction(() => window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode === "fallback", {timeout: 3000});
  const fallbackContract = await page.evaluate(() => {
    const runtime = window.__SLIDE_MEDIA_PLAYBACK__;
    const shell = runtime.fullscreenShell;
    const button = shell.querySelector("[data-video-fullscreen]");
    const video = shell.querySelector("video");
    return {
      overlayVisible: !document.querySelector(".video-fullscreen-overlay")?.hidden,
      shellInOverlay: shell.parentElement?.classList.contains("video-fullscreen-overlay"),
      fullscreenClass: shell.classList.contains("is-video-fullscreen"),
      fallbackClass: shell.classList.contains("is-fallback-fullscreen"),
      pressed: button.getAttribute("aria-pressed"),
      label: button.getAttribute("aria-label"),
      currentTime: video.currentTime,
      role: runtime.overlay.getAttribute("role"),
      modal: runtime.overlay.getAttribute("aria-modal"),
      backgroundInert: document.querySelector(".deck-viewport")?.hasAttribute("inert"),
      activeClose: document.activeElement === shell.querySelector(".video-fullscreen-close"),
    };
  });
  assert.equal(fallbackContract.overlayVisible, true);
  assert.equal(fallbackContract.shellInOverlay, true);
  assert.equal(fallbackContract.fullscreenClass, true);
  assert.equal(fallbackContract.fallbackClass, true);
  assert.equal(fallbackContract.pressed, "true");
  assert.equal(fallbackContract.label?.startsWith("退出全屏"), true);
  assert.equal(fallbackContract.role, "dialog");
  assert.equal(fallbackContract.modal, "true");
  assert.equal(fallbackContract.backgroundInert, true);
  assert.equal(fallbackContract.activeClose, true);
  assert(fallbackContract.currentTime >= fallbackState.currentTime - 0.05, "fallback fullscreen should preserve playback position");

  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement?.matches(".video-fullscreen-overlay video")), true, "Tab should wrap from close to the fullscreen video");
  await page.keyboard.down("Shift");
  await page.keyboard.press("Tab");
  await page.keyboard.up("Shift");
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains("video-fullscreen-close")), true, "Shift+Tab should remain inside the fallback dialog");

  const savedWhileFullscreen = await page.evaluate(async () => {
    let savedBlob = null;
    const createObjectURL = URL.createObjectURL;
    const revokeObjectURL = URL.revokeObjectURL;
    const anchorClick = HTMLAnchorElement.prototype.click;
    URL.createObjectURL = blob => {
      savedBlob = blob;
      return "blob:media-playback-test";
    };
    URL.revokeObjectURL = () => {};
    HTMLAnchorElement.prototype.click = () => {};
    try {
      window.__SLIDE_PRESENTATION__.save();
      const source = await savedBlob.text();
      const saved = new DOMParser().parseFromString(source, "text/html");
      return {
        shells: saved.querySelectorAll("[data-slide-video-shell]").length,
        videos: saved.querySelectorAll("[data-slide-video]").length,
        buttons: saved.querySelectorAll("[data-video-fullscreen]").length,
        overlays: saved.querySelectorAll(".video-fullscreen-overlay").length,
        transient: saved.querySelectorAll(".is-video-fullscreen,.is-fallback-fullscreen").length,
        backgroundMarkers: saved.querySelectorAll("[data-video-fullscreen-background]").length,
        viewportInert: saved.querySelector(".deck-viewport")?.hasAttribute("inert"),
        statusInert: saved.querySelector(".deck-status")?.hasAttribute("inert"),
        statusAriaHidden: saved.querySelector(".deck-status")?.getAttribute("aria-hidden"),
      };
    } finally {
      URL.createObjectURL = createObjectURL;
      URL.revokeObjectURL = revokeObjectURL;
      HTMLAnchorElement.prototype.click = anchorClick;
    }
  });
  assert.deepEqual(savedWhileFullscreen, {
    shells: 5,
    videos: 5,
    buttons: 0,
    overlays: 0,
    transient: 0,
    backgroundMarkers: 0,
    viewportInert: false,
    statusInert: true,
    statusAriaHidden: "false",
  });

  await page.evaluate(() => {
    const shell = window.__SLIDE_MEDIA_PLAYBACK__.fullscreenShell;
    window.__mediaFullscreenMock.element = shell;
    document.dispatchEvent(new Event("fullscreenchange"));
  });
  await page.waitForFunction(() => window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode === "native-shell");
  assert.deepEqual(await page.evaluate(() => {
    const runtime = window.__SLIDE_MEDIA_PLAYBACK__;
    return {
      overlayHidden: runtime.overlay.hidden,
      backgroundInert: document.querySelector(".deck-viewport")?.hasAttribute("inert"),
      statusInert: document.querySelector(".deck-status")?.hasAttribute("inert"),
      statusAriaHidden: document.querySelector(".deck-status")?.getAttribute("aria-hidden"),
      shellRestored: runtime.fullscreenShell?.parentNode === window.__mediaFallbackOrigin.parent,
      activeClose: document.activeElement?.classList.contains("video-fullscreen-close"),
    };
  }), {overlayHidden: true, backgroundInert: false, statusInert: true, statusAriaHidden: "false", shellRestored: true, activeClose: true});
  await page.evaluate(() => window.__SLIDE_MEDIA_PLAYBACK__.exitFullscreen());
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);
  await page.click(standaloneFullscreen);
  await page.waitForFunction(() => window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode === "fallback", {timeout: 3000});

  await page.focus(".video-fullscreen-overlay [data-slide-video]");
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.evaluate(() => window.__SLIDE_PRESENTATION__.current), fallbackState.slideIndex, "slide navigation should be suspended during video fullscreen");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);
  const restoredFallback = await page.evaluate(() => {
    const shell = document.querySelector("[data-slide-id='video'] [data-slide-video-shell]");
    const video = shell.querySelector("video");
    return {
      parent: shell.parentNode === window.__mediaFallbackOrigin.parent,
      next: shell.nextSibling === window.__mediaFallbackOrigin.next,
      overlayHidden: document.querySelector(".video-fullscreen-overlay")?.hidden === true,
      transient: shell.matches(".is-video-fullscreen,.is-fallback-fullscreen"),
      currentTime: video.currentTime,
    };
  });
  assert.equal(restoredFallback.parent && restoredFallback.next && restoredFallback.overlayHidden && !restoredFallback.transient, true);
  assert(restoredFallback.currentTime >= fallbackState.currentTime - 0.05, "Escape should not reset playback position");
  await page.$eval(".deck-status", node => {
    node.removeAttribute("inert");
    node.removeAttribute("aria-hidden");
  });

  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(2, false));
  await page.click("[data-slide-id='tabbed-autoplay-video'] [data-media-target='1']");
  await page.$eval(tabbedShell, shell => {
    shell.requestFullscreen = () => new Promise(() => {});
  });
  await page.click(`${tabbedShell} [data-video-fullscreen]`);
  await page.waitForFunction(() => window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode === "fallback", {timeout: 3000});
  assert.equal(
    await page.$eval("[data-slide-id='tabbed-autoplay-video'] [data-media-target].active", button => button.dataset.mediaTarget),
    "1",
    "entering fullscreen should preserve the active Gallery tab"
  );
  await page.$eval("[data-slide-id='tabbed-autoplay-video'] [data-media-target='0']", button => button.click());
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);
  await page.waitForFunction(selector => document.querySelector(selector)?.paused === true, {}, tabbedVideo);
  assert.equal(await page.$eval("[data-slide-id='tabbed-autoplay-video'] [data-media-target].active", button => button.dataset.mediaTarget), "0");

  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(1, false));
  await page.$eval("[data-slide-id='after-video'] [data-slide-video-shell]", shell => {
    shell.requestFullscreen = () => new Promise(() => {});
  });
  await page.click("[data-slide-id='after-video'] [data-video-fullscreen]");
  await page.waitForFunction(() => window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode === "fallback", {timeout: 3000});
  assert.equal(await page.$eval(".video-fullscreen-overlay [data-slide-video]", video => !video.paused && video.autoplay && video.loop && video.muted), true);
  await page.evaluate(() => window.__SLIDE_LAYOUT_EDITOR__.setActive(true));
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);
  assert.equal(await page.$eval("body", body => body.classList.contains("editor-open")), true);
  await page.evaluate(() => window.__SLIDE_LAYOUT_EDITOR__.setActive(false));

  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(3, false));
  const gridOrderBefore = await page.$$eval(gridVideos, videos => videos.map(video => video.getAttribute("aria-label")));
  await page.$eval("[data-slide-id='grid-manual-videos'] [data-slide-video-shell]", shell => {
    shell.requestFullscreen = () => new Promise(() => {});
  });
  await page.click("[data-slide-id='grid-manual-videos'] [data-video-fullscreen]");
  await page.waitForFunction(() => window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode === "fallback", {timeout: 3000});
  await page.click(".video-fullscreen-overlay .video-fullscreen-close");
  await page.waitForFunction(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen);
  assert.deepEqual(await page.$$eval(gridVideos, videos => videos.map(video => video.getAttribute("aria-label"))), gridOrderBefore);

  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(2, false));
  await page.click("[data-slide-id='tabbed-autoplay-video'] [data-media-target='1']");
  await page.click(`${tabbedShell} [data-video-fullscreen]`);
  await page.waitForFunction(() => window.__SLIDE_MEDIA_PLAYBACK__.fullscreenMode === "fallback", {timeout: 3000});

  const staticExportMarkup = await page.evaluate(async () => {
    const feature = window.__SLIDE_STATIC_EXPORT__;
    const entry = feature.snapshotPlan().find(candidate => (
      candidate.slideId === "tabbed-autoplay-video" && candidate.selections[0]?.target === "1"
    ));
    const serialize = XMLSerializer.prototype.serializeToString;
    let markup = "";
    XMLSerializer.prototype.serializeToString = function(node) {
      markup = node.outerHTML || "";
      return serialize.call(this, node);
    };
    try {
      await feature.renderFrame(entry);
      return markup;
    } finally {
      XMLSerializer.prototype.serializeToString = serialize;
    }
  });
  assert.doesNotMatch(staticExportMarkup, /data-video-fullscreen|video-fullscreen-overlay|is-video-fullscreen|is-fallback-fullscreen/);
  assert.equal((staticExportMarkup.match(/static-export-video-frame/g) || []).length, 1, "static capture should restore and freeze the active Gallery video");
  assert.equal(await page.evaluate(() => !window.__SLIDE_MEDIA_PLAYBACK__.isFullscreen), true, "static capture should exit live fallback fullscreen first");
  assert.equal(await page.$eval("[data-slide-id='tabbed-autoplay-video'] [data-media-target].active", button => button.dataset.mediaTarget), "1");

  await page.setViewport({width: 1280, height: 720, deviceScaleFactor: 1});
  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(0, false));
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const laptopControl = await page.$eval(standaloneFullscreen, button => {
    const bounds = button.getBoundingClientRect();
    return {
      width: bounds.width,
      height: bounds.height,
      insideViewport: bounds.left >= 0 && bounds.top >= 0 && bounds.right <= innerWidth && bounds.bottom <= innerHeight,
    };
  });
  assert(
    laptopControl.width >= 44 && laptopControl.height >= 44 && laptopControl.insideViewport,
    `1280×720 fullscreen control should remain a visible 44px target: ${JSON.stringify(laptopControl)}`
  );

  await page.setViewport({width: 375, height: 800, deviceScaleFactor: 1});
  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(0, false));
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const mobileStandaloneControl = await page.$eval(standaloneFullscreen, button => {
    const bounds = button.getBoundingClientRect();
    const style = getComputedStyle(button);
    return {
      width: bounds.width,
      height: bounds.height,
      display: style.display,
      visibility: style.visibility,
      insideViewport: bounds.left >= 0 && bounds.top >= 0 && bounds.right <= innerWidth && bounds.bottom <= innerHeight,
    };
  });
  assert(
    mobileStandaloneControl.width >= 44 && mobileStandaloneControl.height >= 44,
    `375×800 standalone fullscreen control should remain at least 44px: ${JSON.stringify(mobileStandaloneControl)}`
  );
  assert.equal(mobileStandaloneControl.display !== "none" && mobileStandaloneControl.visibility === "visible" && mobileStandaloneControl.insideViewport, true);

  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(3, false));
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const mobileGridControls = await page.$$eval("[data-slide-id='grid-manual-videos'] [data-video-fullscreen]", buttons => buttons.map(button => {
    const bounds = button.getBoundingClientRect();
    const style = getComputedStyle(button);
    return {
      width: bounds.width,
      height: bounds.height,
      display: style.display,
      visibility: style.visibility,
      insideViewport: bounds.left >= 0 && bounds.top >= 0 && bounds.right <= innerWidth && bounds.bottom <= innerHeight,
    };
  }));
  assert.equal(mobileGridControls.length, 2);
  assert(
    mobileGridControls.every(control => (
      control.width >= 44 && control.height >= 44 && control.display !== "none" && control.visibility === "visible" && control.insideViewport
    )),
    `375×800 Gallery fullscreen controls should remain visible 44px targets: ${JSON.stringify(mobileGridControls)}`
  );

  assert.equal(await page.evaluate(() => Boolean(window.__SLIDE_MEDIA_PLAYBACK__)), true);

  console.log("Media playback browser test passed.");
} finally {
  if (browser) await browser.close();
  await rm(outputRoot, {recursive: true, force: true});
}
