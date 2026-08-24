import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import puppeteer from "puppeteer";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const harnessSource = resolve(projectRoot, "harnesses/static-export/slides.md");
const workRoot = resolve(projectRoot, "work");
await mkdir(workRoot, {recursive: true});
const outputRoot = await mkdtemp(resolve(workRoot, "static-export-"));
const output = resolve(outputRoot, "index.html");
const downloadRoot = resolve(outputRoot, "downloads");
await mkdir(downloadRoot);
const pythonExecutable = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const execFileAsync = promisify(execFile);
const executablePath = [
  process.env.PUPPETEER_EXECUTABLE_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].find(candidate => candidate && existsSync(candidate));
let browser = null;

function crc32(bytes) {
  const table = Uint32Array.from({length: 256}, (_, index) => {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) value = (value & 1) ? (0xedb88320 ^ (value >>> 1)) : (value >>> 1);
    return value >>> 0;
  });
  let crc = 0xffffffff;
  for (const byte of bytes) crc = table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function parseZip(buffer) {
  const bytes = new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const decoder = new TextDecoder();
  let eocd = -1;
  for (let offset = bytes.length - 22; offset >= Math.max(0, bytes.length - 65557); offset -= 1) {
    if (view.getUint32(offset, true) === 0x06054b50) {
      eocd = offset;
      break;
    }
  }
  assert(eocd >= 0, "PPTX should contain an end-of-central-directory record");
  const count = view.getUint16(eocd + 10, true);
  const centralSize = view.getUint32(eocd + 12, true);
  const centralOffset = view.getUint32(eocd + 16, true);
  assert.equal(centralOffset + centralSize, eocd);
  const entries = new Map();
  let offset = 0;
  while (offset < centralOffset) {
    assert.equal(view.getUint32(offset, true), 0x04034b50, `invalid local ZIP header at ${offset}`);
    const flags = view.getUint16(offset + 6, true);
    const method = view.getUint16(offset + 8, true);
    const checksum = view.getUint32(offset + 14, true);
    const compressedSize = view.getUint32(offset + 18, true);
    const uncompressedSize = view.getUint32(offset + 22, true);
    const nameLength = view.getUint16(offset + 26, true);
    const extraLength = view.getUint16(offset + 28, true);
    assert.equal(method, 0, "runtime PPTX writer should use deterministic store-only ZIP entries");
    assert.equal(flags & 0x0800, 0x0800, "ZIP entry names should be UTF-8");
    assert.equal(compressedSize, uncompressedSize);
    const name = decoder.decode(bytes.subarray(offset + 30, offset + 30 + nameLength));
    assert(!name.startsWith("/") && !name.split("/").includes(".."), `unsafe ZIP path: ${name}`);
    assert(!entries.has(name), `duplicate ZIP part: ${name}`);
    const start = offset + 30 + nameLength + extraLength;
    const data = bytes.slice(start, start + compressedSize);
    assert.equal(crc32(data), checksum, `CRC mismatch for ${name}`);
    entries.set(name, data);
    offset = start + compressedSize;
  }
  assert.equal(offset, centralOffset);
  assert.equal(entries.size, count);
  let centralCursor = centralOffset;
  for (let index = 0; index < count; index += 1) {
    assert.equal(view.getUint32(centralCursor, true), 0x02014b50, `invalid central ZIP header at ${centralCursor}`);
    const nameLength = view.getUint16(centralCursor + 28, true);
    const extraLength = view.getUint16(centralCursor + 30, true);
    const commentLength = view.getUint16(centralCursor + 32, true);
    const name = decoder.decode(bytes.subarray(centralCursor + 46, centralCursor + 46 + nameLength));
    assert(entries.has(name), `central directory references missing part: ${name}`);
    centralCursor += 46 + nameLength + extraLength + commentLength;
  }
  assert.equal(centralCursor, eocd);
  return entries;
}

function jpegDimensions(bytes) {
  assert.equal(bytes[0], 0xff);
  assert.equal(bytes[1], 0xd8);
  let offset = 2;
  while (offset + 9 < bytes.length) {
    while (bytes[offset] === 0xff) offset += 1;
    const marker = bytes[offset];
    offset += 1;
    if (marker === 0xd8 || marker === 0xd9) continue;
    const length = (bytes[offset] << 8) | bytes[offset + 1];
    if (new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]).has(marker)) {
      return {height: (bytes[offset + 3] << 8) | bytes[offset + 4], width: (bytes[offset + 5] << 8) | bytes[offset + 6]};
    }
    offset += length;
  }
  throw new Error("JPEG dimensions were not found");
}

function waitForDownload(client, extension) {
  return new Promise((resolveDownload, rejectDownload) => {
    let guid = "";
    let filename = "";
    const cleanup = () => {
      clearTimeout(timeout);
      client.off("Browser.downloadWillBegin", onBegin);
      client.off("Browser.downloadProgress", onProgress);
    };
    const onBegin = event => {
      if (!event.suggestedFilename.endsWith(extension)) return;
      guid = event.guid;
      filename = event.suggestedFilename;
    };
    const onProgress = event => {
      if (!guid || event.guid !== guid) return;
      if (event.state === "canceled") {
        cleanup();
        rejectDownload(new Error(`${extension} download was canceled`));
      } else if (event.state === "completed") {
        cleanup();
        resolveDownload({filename, path: resolve(downloadRoot, filename)});
      }
    };
    const timeout = setTimeout(() => {
      cleanup();
      rejectDownload(new Error(`timed out waiting for ${extension} download`));
    }, 60000);
    client.on("Browser.downloadWillBegin", onBegin);
    client.on("Browser.downloadProgress", onProgress);
  });
}

try {
  await execFileAsync(
    pythonExecutable,
    [resolve(projectRoot, "build_slides.py"), harnessSource, "-o", output, "--strict"],
    {cwd: projectRoot, windowsHide: true}
  );
  browser = await puppeteer.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage();
  await page.setViewport({width: 1920, height: 1080, deviceScaleFactor: 1});
  const consoleIssues = [];
  const networkRequests = [];
  page.on("console", message => {
    if (["error", "warning"].includes(message.type())) consoleIssues.push(`${message.type()}: ${message.text()}`);
  });
  page.on("pageerror", error => consoleIssues.push(`pageerror: ${error.message}`));
  page.on("request", request => {
    if (/^https?:/i.test(request.url())) networkRequests.push(request.url());
  });
  await page.goto(pathToFileURL(output).href, {waitUntil: "load"});
  await page.waitForFunction(() => Boolean(window.__SLIDE_STATIC_EXPORT__));

  assert.equal(await page.evaluate(() => window.__SLIDE_STATIC_EXPORT__.slides.length), 3);
  assert.deepEqual(await page.evaluate(() => window.__SLIDE_STATIC_EXPORT__.snapshotPlan().map(entry => ({
    slideId: entry.slideId,
    targets: entry.selections.map(selection => selection.target)
  }))), [
    {slideId: "export-text", targets: []},
    {slideId: "export-gallery", targets: ["0"]},
    {slideId: "export-gallery", targets: ["1"]},
    {slideId: "export-video", targets: []}
  ]);
  assert.equal(await page.$eval('[data-editor-category="advanced"]', node => node.open), false);
  assert.equal(await page.$eval("#editorExportPdf", node => node.checkVisibility()), false);

  await page.keyboard.press("e");
  await page.waitForFunction(() => document.body.classList.contains("editor-open"));
  await page.waitForFunction(() => document.getElementById("layoutEditorPanel").getBoundingClientRect().right <= innerWidth + 1);
  await page.click('[data-editor-category="advanced"] > summary');
  assert.equal(await page.$eval('[data-editor-category="advanced"]', node => node.open), true);
  assert.equal(await page.$eval("#editorExportPdf", node => node.checkVisibility()), true);
  assert.equal(await page.$eval("#editorExportPptx", node => node.checkVisibility()), true);
  assert.match(await page.$eval("#editorStaticExportHelp", node => node.textContent), /静态|无动效/);

  const revealStatic = await page.evaluate(async () => {
    const feature = window.__SLIDE_STATIC_EXPORT__;
    const entry = feature.snapshotPlan()[0];
    const nodes = [...entry.slide.querySelectorAll(".reveal")];
    const previous = nodes.map(node => node.getAttribute("style"));
    nodes.forEach(node => { node.style.opacity = "0"; node.style.transform = "translateY(300px)"; });
    const hidden = await feature.renderFrame(entry);
    nodes.forEach((node, index) => previous[index] === null ? node.removeAttribute("style") : node.setAttribute("style", previous[index]));
    const final = await feature.renderFrame(entry);
    const hash = async bytes => [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(value => value.toString(16).padStart(2, "0")).join("");
    return {hidden: await hash(hidden.bytes), final: await hash(final.bytes), width: hidden.width, height: hidden.height};
  });
  assert.equal(revealStatic.hidden, revealStatic.final, "export override should render the final reveal state regardless of live opacity/transform");
  assert.deepEqual({width: revealStatic.width, height: revealStatic.height}, {width: 1920, height: 1080});

  await page.evaluate(() => window.__SLIDE_PRESENTATION__.show(1, false));
  await page.click('[data-slide-id="export-gallery"] [data-media-target="1"]');
  const beforeState = await page.evaluate(() => ({
    current: window.__SLIDE_PRESENTATION__.current,
    hash: location.hash,
    bodyClasses: [...document.body.classList].sort(),
    galleryTarget: document.querySelector('[data-slide-id="export-gallery"] [data-media-target].active')?.dataset.mediaTarget,
    editorOpen: document.body.classList.contains("editor-open"),
    advancedOpen: document.querySelector('[data-editor-category="advanced"]').open,
    storage: JSON.stringify({...localStorage})
  }));

  const client = await page.createCDPSession();
  await client.send("Browser.setDownloadBehavior", {behavior: "allow", downloadPath: downloadRoot, eventsEnabled: true});
  const pdfDownload = waitForDownload(client, ".pdf");
  await page.click("#editorExportPdf");
  await page.waitForFunction(() => window.__SLIDE_STATIC_EXPORT__.busy);
  assert.equal(await page.$eval("#editorExportPdf", node => node.disabled && node.getAttribute("aria-busy") === "true"), true);
  assert.equal(await page.$eval("#editorStaticExportProgress", node => !node.hidden), true);
  const concurrentMessage = await page.evaluate(async () => {
    try {
      await window.__SLIDE_STATIC_EXPORT__.exportPptx({download: false});
      return "";
    } catch (error) {
      return error.message;
    }
  });
  assert.match(concurrentMessage, /正在进行/);
  const downloadedPdf = await pdfDownload;
  await page.waitForFunction(() => !window.__SLIDE_STATIC_EXPORT__.busy);
  assert.equal(downloadedPdf.filename, "Static Export Harness.pdf");
  const pdf = await readFile(downloadedPdf.path);
  assert.equal(pdf.subarray(0, 8).toString("latin1"), "%PDF-1.4");
  assert.match(pdf.subarray(-32).toString("latin1"), /%%EOF\s*$/);
  const pdfStructure = pdf.toString("latin1").replace(/stream\r?\n[\s\S]*?\r?\n?endstream/g, "stream endstream");
  assert.equal((pdfStructure.match(/\/Type \/Page\b/g) || []).length, 4);
  assert.match(pdfStructure, /\/Type \/Pages \/Count 4/);
  assert.equal((pdfStructure.match(/\/MediaBox \[0 0 960 540\]/g) || []).length, 4);
  assert(!/\/JavaScript|\/RichMedia|\/Movie/.test(pdfStructure));

  const pptxDownload = waitForDownload(client, ".pptx");
  await page.click("#editorExportPptx");
  const downloadedPptx = await pptxDownload;
  await page.waitForFunction(() => !window.__SLIDE_STATIC_EXPORT__.busy);
  assert.equal(downloadedPptx.filename, "Static Export Harness.pptx");
  const pptx = await readFile(downloadedPptx.path);
  assert.deepEqual([...pptx.subarray(0, 4)], [0x50, 0x4b, 0x03, 0x04]);
  const parts = parseZip(pptx);
  [
    "[Content_Types].xml", "_rels/.rels", "docProps/core.xml", "docProps/app.xml",
    "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels", "ppt/slideMasters/slideMaster1.xml",
    "ppt/slideMasters/_rels/slideMaster1.xml.rels", "ppt/slideLayouts/slideLayout1.xml",
    "ppt/slideLayouts/_rels/slideLayout1.xml.rels", "ppt/theme/theme1.xml"
  ].forEach(name => assert(parts.has(name), `PPTX should contain ${name}`));
  const decode = name => new TextDecoder().decode(parts.get(name));
  const presentationXml = decode("ppt/presentation.xml");
  assert.equal((presentationXml.match(/<p:sldId /g) || []).length, 4);
  assert.match(presentationXml, /<p:sldSz cx="12192000" cy="6858000" type="screen16x9"\/>/);
  assert.match(decode("docProps/app.xml"), /<Slides>4<\/Slides>/);
  assert.match(decode("ppt/slideMasters/slideMaster1.xml"), /<p:sldLayoutId id="2147483649" r:id="rId1"\/>/);
  for (let number = 1; number <= 4; number += 1) {
    const slideName = `ppt/slides/slide${number}.xml`;
    const relsName = `ppt/slides/_rels/slide${number}.xml.rels`;
    const imageName = `ppt/media/image${number}.jpeg`;
    assert(parts.has(slideName) && parts.has(relsName) && parts.has(imageName));
    const slideXml = decode(slideName);
    assert.equal((slideXml.match(/<p:pic>/g) || []).length, 1);
    assert.match(slideXml, /<a:off x="0" y="0"\/><a:ext cx="12192000" cy="6858000"\/>/);
    assert(!/<p:(?:timing|transition)\b/.test(slideXml));
    assert.match(decode(relsName), new RegExp(`Target="\\.\\./media/image${number}\\.jpeg"`));
    assert.deepEqual(jpegDimensions(parts.get(imageName)), {width: 1920, height: 1080});
  }
  assert.equal([...parts.keys()].some(name => /\.(?:mp4|webm)$/i.test(name)), false);
  assert.equal([...parts.values()].some(bytes => /relationships\/(?:video|media)/.test(new TextDecoder().decode(bytes))), false);

  const afterState = await page.evaluate(() => ({
    current: window.__SLIDE_PRESENTATION__.current,
    hash: location.hash,
    bodyClasses: [...document.body.classList].sort(),
    galleryTarget: document.querySelector('[data-slide-id="export-gallery"] [data-media-target].active')?.dataset.mediaTarget,
    editorOpen: document.body.classList.contains("editor-open"),
    advancedOpen: document.querySelector('[data-editor-category="advanced"]').open,
    storage: JSON.stringify({...localStorage})
  }));
  assert.deepEqual(afterState, beforeState, "static export should not mutate live presentation/editor/Gallery/storage state");
  assert.deepEqual((await readdir(downloadRoot)).sort(), ["Static Export Harness.pdf", "Static Export Harness.pptx"]);

  await page.setViewport({width: 375, height: 800, deviceScaleFactor: 1});
  await new Promise(resolveDelay => setTimeout(resolveDelay, 280));
  const compact = await page.evaluate(async () => {
    const panel = document.getElementById("layoutEditorPanel").getBoundingClientRect();
    const buttons = [...document.querySelectorAll(".static-export-actions .editor-button")].map(button => {
      const rect = button.getBoundingClientRect();
      return {left: rect.left, right: rect.right};
    });
    const frame = await window.__SLIDE_STATIC_EXPORT__.renderFrame(window.__SLIDE_STATIC_EXPORT__.snapshotPlan()[0]);
    return {panelLeft: panel.left, panelRight: panel.right, viewport: innerWidth, buttons, width: frame.width, height: frame.height};
  });
  assert(compact.panelLeft >= -1 && compact.panelRight <= compact.viewport + 1, JSON.stringify(compact));
  assert(compact.buttons.every(button => button.left >= compact.panelLeft - 1 && button.right <= compact.panelRight + 1), JSON.stringify(compact));
  assert.deepEqual({width: compact.width, height: compact.height}, {width: 1920, height: 1080});

  const budgetFailure = await page.evaluate(async () => {
    const feature = window.__SLIDE_STATIC_EXPORT__;
    const originalLimit = feature.rasterByteLimit;
    feature.rasterByteLimit = 1;
    let message = "";
    try { await feature.renderFrames([feature.snapshotPlan()[0]]); } catch (error) { message = error.message; }
    feature.rasterByteLimit = originalLimit;
    return message;
  });
  assert.match(budgetFailure, /超过 512 MB/);

  const failure = await page.evaluate(async () => {
    const feature = window.__SLIDE_STATIC_EXPORT__;
    const original = feature.sanitizeClone;
    feature.sanitizeClone = () => { throw new Error("测试导出失败"); };
    let message = "";
    try { await feature.exportPdf({download: false}); } catch (error) { message = error.message; }
    feature.sanitizeClone = original;
    return {
      message,
      status: document.getElementById("editorStaticExportStatus").textContent,
      state: document.getElementById("editorStaticExportStatus").dataset.state,
      buttonsEnabled: [...document.querySelectorAll("#editorExportPdf,#editorExportPptx")].every(button => !button.disabled)
    };
  });
  assert.match(failure.message, /测试导出失败/);
  assert.match(failure.status, /导出失败/);
  assert.equal(failure.state, "error");
  assert.equal(failure.buttonsEnabled, true);
  assert.deepEqual((await readdir(downloadRoot)).sort(), ["Static Export Harness.pdf", "Static Export Harness.pptx"]);
  assert.deepEqual(networkRequests, []);
  assert.deepEqual(consoleIssues, []);

  console.log("Static PDF/PPTX export browser test passed.");
} finally {
  if (browser) await browser.close();
  await rm(outputRoot, {recursive: true, force: true});
}
