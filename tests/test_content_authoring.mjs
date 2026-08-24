import assert from "node:assert/strict";
import {execFile} from "node:child_process";
import {existsSync} from "node:fs";
import {mkdir, mkdtemp, rm} from "node:fs/promises";
import {dirname, resolve} from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";
import {promisify} from "node:util";
import puppeteer from "puppeteer";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const harnessSource = resolve(projectRoot, "harnesses/content-authoring/slides.md");
const workRoot = resolve(projectRoot, "work");
await mkdir(workRoot, {recursive: true});
const outputRoot = await mkdtemp(resolve(workRoot, "content-authoring-"));
const output = resolve(outputRoot, "index.html");
const pythonExecutable = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const execFileAsync = promisify(execFile);
const executablePath = [
  process.env.PUPPETEER_EXECUTABLE_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].find(candidate => candidate && existsSync(candidate));
let browser = null;

try {
  await execFileAsync(
    pythonExecutable,
    [resolve(projectRoot, "build_slides.py"), harnessSource, "-o", output, "--strict"],
    {cwd: projectRoot, windowsHide: true}
  );
  browser = await puppeteer.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const page = await browser.newPage();
  await page.setViewport({width: 1920, height: 1080, deviceScaleFactor: 1});
  await page.goto(pathToFileURL(output).href, {waitUntil: "load"});
  await page.waitForFunction(() => Boolean(window.__SLIDE_CONTENT_AUTHORING__));

  assert.equal(await page.$$eval(".slide[data-slide-kind='content']", nodes => nodes.length), 3);
  assert.equal(await page.$$eval("[data-author-item-id]", nodes => new Set(nodes.map(node => node.dataset.authorItemId)).size === nodes.length), true);

  const cacheKeys = await page.evaluate(() => ({
    legacy: window.__SLIDE_PRESENTATION__.storageKey(),
    layout: window.__SLIDE_LAYOUT_EDITOR__.storageKey()
  }));
  await page.evaluate(keys => {
    localStorage.setItem(keys.legacy, JSON.stringify({
      0: "LEGACY_NUMERIC_TITLE_SHOULD_NOT_APPEAR",
      1: "LEGACY_NUMERIC_BODY_SHOULD_NOT_APPEAR"
    }));
    localStorage.setItem(keys.layout, JSON.stringify({
      sourceHash: "0".repeat(64),
      slides: {"authoring-first": {layout: "gallery", regions: {content: {x: 0, y: 0, width: 48, height: 48}}}}
    }));
  }, cacheKeys);
  await page.reload({waitUntil: "load"});
  await page.waitForFunction(() => Boolean(window.__SLIDE_CONTENT_AUTHORING__));
  assert.equal(await page.$eval("[data-slide-id='authoring-first'] h1", node => node.textContent.trim()), "稳定文字字段");
  assert.equal(await page.$eval("body", node => node.textContent.includes("LEGACY_NUMERIC_")), false);
  assert.equal(await page.evaluate(() => Boolean(window.__SLIDE_LAYOUT_EDITOR__.entries["authoring-first"])), false);
  assert.match(await page.evaluate(() => window.__SLIDE_LAYOUT_EDITOR__.storageWarning), /旧源码/);
  await page.evaluate(keys => {
    localStorage.removeItem(keys.legacy);
    localStorage.removeItem(keys.layout);
  }, cacheKeys);

  const preferredRegions = await page.evaluate(() => {
    const editor = window.__SLIDE_LAYOUT_EDITOR__;
    const presentation = window.__SLIDE_PRESENTATION__;
    const snapshot = () => ({
      selected: editor.selectedRegion,
      tab: document.querySelector(".editor-region-tab.active")?.dataset.region || "",
      box: document.querySelector(".slide.active .layout-region-box.active")?.dataset.region || ""
    });
    presentation.show(0, false);
    editor.setActive(true);
    const textPage = snapshot();
    editor.selectRegion("content");
    const explicitOverall = snapshot();
    presentation.show(0, false);
    const overallAfterSamePageShow = snapshot();
    editor.applyPreset();
    const overallAfterCommit = snapshot();
    editor.setActive(true);
    const overallAfterRepeatedOpen = snapshot();
    editor.setActive(false);
    editor.setActive(true);
    const reopenedTextPage = snapshot();
    editor.changeLayout("split");
    const changedToSplit = snapshot();
    editor.selectRegion("content");
    editor.resetPage();
    const resetTextPage = snapshot();
    presentation.show(1, false);
    const galleryPageAfterNavigation = snapshot();
    editor.setActive(false);
    editor.setActive(true);
    const reopenedGalleryPage = snapshot();
    editor.setActive(false);
    presentation.show(0, false);
    return {textPage, explicitOverall, overallAfterSamePageShow, overallAfterCommit, overallAfterRepeatedOpen, reopenedTextPage, changedToSplit, resetTextPage, galleryPageAfterNavigation, reopenedGalleryPage};
  });
  assert.deepEqual(preferredRegions.textPage, {selected: "copy", tab: "copy", box: "copy"});
  assert.deepEqual(preferredRegions.explicitOverall, {selected: "content", tab: "content", box: "content"});
  assert.deepEqual(preferredRegions.overallAfterSamePageShow, {selected: "content", tab: "content", box: "content"});
  assert.deepEqual(preferredRegions.overallAfterCommit, {selected: "content", tab: "content", box: "content"});
  assert.deepEqual(preferredRegions.overallAfterRepeatedOpen, {selected: "content", tab: "content", box: "content"});
  assert.deepEqual(preferredRegions.reopenedTextPage, {selected: "copy", tab: "copy", box: "copy"});
  assert.deepEqual(preferredRegions.changedToSplit, {selected: "visual", tab: "visual", box: "visual"});
  assert.deepEqual(preferredRegions.resetTextPage, {selected: "copy", tab: "copy", box: "copy"});
  assert.deepEqual(preferredRegions.galleryPageAfterNavigation, {selected: "visual", tab: "visual", box: "visual"});
  assert.deepEqual(preferredRegions.reopenedGalleryPage, {selected: "visual", tab: "visual", box: "visual"});

  const pureImageRegion = await page.evaluate(() => {
    const editor = window.__SLIDE_LAYOUT_EDITOR__;
    const slide = document.createElement("section");
    slide.className = "slide cover-slide pure-image-slide";
    slide.dataset.slideKind = "cover";
    slide.dataset.slideId = "synthetic-pure-image";
    slide.dataset.generatedLayout = "hero-split";
    const figure = document.createElement("figure");
    figure.className = "pure-image-shell";
    slide.appendChild(figure);
    document.body.appendChild(slide);
    const entry = {layout: "auto", regions: editor.presetRegions(slide, "hero-split")};
    const parts = editor.actualParts(slide);
    const result = {
      preferred: editor.preferredRegion(slide, entry),
      contentIsImage: parts.content === figure,
      visualIsImage: parts.visual === figure,
      regions: entry.regions
    };
    slide.remove();
    return result;
  });
  assert.equal(pureImageRegion.preferred, "visual");
  assert.equal(pureImageRegion.contentIsImage, true);
  assert.equal(pureImageRegion.visualIsImage, true);
  assert.deepEqual(pureImageRegion.regions, {
    content: {x: 0, y: 0, width: 1920, height: 1080},
    visual: {x: 0, y: 0, width: 1920, height: 1080}
  });

  const interaction = await page.evaluate(async () => {
    const feature = window.__SLIDE_CONTENT_AUTHORING__;
    feature.setActive(true);
    const first = feature.slideStates.get("authoring-first");
    const gallery = feature.slideStates.get("authoring-gallery");
    const target = feature.slideStates.get("authoring-target");
    const firstTextId = first.itemIds.find(id => feature.items.get(id)?.kind === "text");
    const calloutId = first.itemIds.find(id => feature.items.get(id)?.kind === "callout");
    const addedId = feature.addTextBlock(first.id, {}, {select: false});
    const added = feature.itemSnapshot(feature.items.get(addedId));

    feature.reorderItem(first.id, calloutId, firstTextId);
    const blockOrder = feature.blockItemIds(first);
    const domBlockOrder = [...first.element.querySelectorAll('[data-author-item-kind="text"],[data-author-item-kind="callout"]')]
      .map(node => node.dataset.authorItemId);

    feature.setGalleryDisplay(gallery.id, "tabs");
    const markdownWithTabs = feature.serializeMarkdown();
    const tabsView = {
      panels: gallery.element.querySelectorAll("[data-media-panel]").length,
      buttons: gallery.element.querySelectorAll("[data-media-target]").length,
      layout: gallery.element.dataset.layoutResolved
    };
    feature.setGalleryDisplay(gallery.id, "grid");
    const gridView = {
      figures: gallery.element.querySelectorAll(".media-grid > [data-author-item-kind='image']").length,
      tabs: gallery.element.querySelectorAll(".media-tabs").length,
      display: gallery.element.dataset.galleryDisplay
    };

    const movedImageId = gallery.itemIds.find(id => feature.items.get(id)?.kind === "image");
    feature.moveItem(movedImageId, target.id, null, {navigate: false});
    const afterImageMove = {
      gallery: {
        media: gallery.element.dataset.mediaCount,
        blocks: gallery.element.dataset.blockCount,
        layout: gallery.element.dataset.layoutResolved
      },
      target: {
        media: target.element.dataset.mediaCount,
        blocks: target.element.dataset.blockCount,
        layout: target.element.dataset.layoutResolved
      }
    };

    feature.moveItem(calloutId, gallery.id, null, {navigate: false});
    const pngBytes = Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="), character => character.charCodeAt(0));
    const imported = await feature.importRasterFiles(
      [new File([pngBytes], "pasted-example.png", {type: "image/png"})],
      {slideId: target.id, intent: "append", source: "test"}
    );
    feature.setGalleryDisplay(target.id, "tabs");
    const importedAssetId = imported.items[0].assetId;
    const markdown = feature.serializeMarkdown({[importedAssetId]: "assets/test/pasted-example.png"});
    const importedItem = feature.items.get(imported.items[0].itemId);
    importedItem.alt = "坏]图\n---";
    importedItem.caption = "引号\"图注\n---";
    const sanitizedMarkdown = feature.serializeMarkdown({[importedAssetId]: "assets/test/pasted-example.png"});
    const insertedDirective = feature.writeSlideDirectives("# 无指令页面\n\n正文", {layout: "gallery", "gallery-display": "tabs"});

    return {
      added,
      firstTextId,
      calloutId,
      addedId,
      blockOrder,
      domBlockOrder,
      tabsView,
      gridView,
      afterImageMove,
      imported,
      targetAfterImport: {
        media: target.element.dataset.mediaCount,
        blocks: target.element.dataset.blockCount,
        layout: target.element.dataset.layoutResolved,
        tabs: target.element.querySelectorAll("[data-media-panel]").length
      },
      pendingAssets: feature.pendingAssets.size,
      layouts: {
        gallery: gallery.layoutResolved,
        target: target.layoutResolved,
        galleryChanged: gallery.layoutChanged,
        targetChanged: target.layoutChanged
      },
      markdownWithTabs,
      markdown,
      sanitizedMarkdown,
      insertedDirective,
      normalizedMixedReplacement: feature.normalizeReplacementNewlines("新\n内容\r\n末尾")
    };
  });

  assert.equal(interaction.added.title, "标题");
  assert.equal(interaction.added.body, "正文");
  assert.equal(interaction.blockOrder[0], interaction.calloutId);
  assert.deepEqual(interaction.domBlockOrder, interaction.blockOrder);
  assert.deepEqual(interaction.tabsView, {panels: 2, buttons: 2, layout: "gallery"});
  assert.deepEqual(interaction.gridView, {figures: 2, tabs: 0, display: "grid"});
  assert.match(interaction.markdownWithTabs, /gallery-display:\s*tabs/);
  assert.deepEqual(interaction.afterImageMove.gallery, {media: "1", blocks: "1", layout: "split"});
  assert.deepEqual(interaction.afterImageMove.target, {media: "1", blocks: "1", layout: "split"});
  assert.equal(interaction.imported.items.length, 1);
  assert.equal(interaction.imported.items[0].replacement, false);
  assert.equal(interaction.pendingAssets, 1);
  assert.deepEqual(interaction.layouts, {gallery: "split", target: "gallery", galleryChanged: true, targetChanged: true});
  assert.deepEqual(interaction.targetAfterImport, {media: "2", blocks: "1", layout: "gallery", tabs: 2});
  assert.match(interaction.markdown, /### 标题\n\n正文/);
  assert.match(interaction.markdown, /> \[!TIP\] 可移动 Callout/);
  assert.match(interaction.markdown, /gallery-display:\s*tabs/);
  assert.match(interaction.markdown, /id: authoring-gallery[\s\S]*?layout: split/);
  assert.match(interaction.markdown, /id: authoring-target[\s\S]*?layout: gallery/);
  assert.match(interaction.markdown, /!\[pasted-example\]\(assets\/test\/pasted-example\.png "pasted-example"\)/);
  assert.match(interaction.sanitizedMarkdown, /!\[坏）图 ---\]\(assets\/test\/pasted-example\.png "引号”图注 ---"\)/);
  assert.match(interaction.insertedDirective, /^<!-- slide\nlayout: gallery\ngallery-display: tabs\n-->\n# 无指令页面/);
  assert.equal(interaction.normalizedMixedReplacement, "新\n内容\n末尾");
  assert(interaction.markdown.indexOf("# 双图展示方式") < interaction.markdown.indexOf("[!TIP] 可移动 Callout"));
  assert(interaction.markdown.indexOf("[!TIP] 可移动 Callout") < interaction.markdown.indexOf("# 跨页移动目标"));

  const saveResult = await page.evaluate(async () => {
    const feature = window.__SLIDE_CONTENT_AUTHORING__;
    const encoder = new TextEncoder();
    const decoder = new TextDecoder();

    class MemoryFileHandle {
      constructor(parent, name) {
        this.kind = "file";
        this.parent = parent;
        this.name = name;
      }
      async getFile() {
        if (!this.parent.files.has(this.name)) throw new DOMException("missing", "NotFoundError");
        return new File([this.parent.files.get(this.name)], this.name);
      }
      async createWritable() {
        let next = new Uint8Array();
        let aborted = false;
        return {
          write: async value => {
            if (value instanceof Blob) next = new Uint8Array(await value.arrayBuffer());
            else if (typeof value === "string") next = encoder.encode(value);
            else if (value instanceof ArrayBuffer) next = new Uint8Array(value.slice(0));
            else if (ArrayBuffer.isView(value)) next = new Uint8Array(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength));
            else throw new TypeError("unsupported write value");
          },
          close: async () => {
            if (!aborted) this.parent.files.set(this.name, next);
          },
          abort: async () => { aborted = true; }
        };
      }
    }

    class MemoryDirectoryHandle {
      constructor(name = "root") {
        this.kind = "directory";
        this.name = name;
        this.files = new Map();
        this.directories = new Map();
      }
      async queryPermission() { return "granted"; }
      async requestPermission() { return "granted"; }
      async getFileHandle(name, options = {}) {
        if (!this.files.has(name)) {
          if (!options.create) throw new DOMException("missing", "NotFoundError");
          this.files.set(name, new Uint8Array());
        }
        return new MemoryFileHandle(this, name);
      }
      async getDirectoryHandle(name, options = {}) {
        if (!this.directories.has(name)) {
          if (!options.create) throw new DOMException("missing", "NotFoundError");
          this.directories.set(name, new MemoryDirectoryHandle(name));
        }
        return this.directories.get(name);
      }
      async removeEntry(name) {
        if (!this.files.delete(name) && !this.directories.delete(name)) throw new DOMException("missing", "NotFoundError");
      }
      seed(path, value) {
        const parts = path.split("/");
        const name = parts.pop();
        let directory = this;
        for (const part of parts) {
          if (!directory.directories.has(part)) directory.directories.set(part, new MemoryDirectoryHandle(part));
          directory = directory.directories.get(part);
        }
        directory.files.set(name, typeof value === "string" ? encoder.encode(value) : new Uint8Array(value));
      }
      read(path) {
        const parts = path.split("/");
        const name = parts.pop();
        let directory = this;
        for (const part of parts) directory = directory.directories.get(part);
        return directory?.files.get(name) || null;
      }
    }

    const changedTarget = feature.slideStates.get("authoring-target");
    feature.layoutEditor.entries[`P${changedTarget.number}`] = {
      layout: "text",
      regions: {
        content: {x: 140, y: 230, width: 1600, height: 650},
        copy: {x: 140, y: 230, width: 1600, height: 650}
      },
      typography: {lineHeight: 1.5, color: "#222222", bold: false}
    };
    const root = new MemoryDirectoryHandle();
    root.seed(feature.source.name, feature.source.text);
    const result = await feature.saveToDirectory(root);
    const sourceEntry = result.changedFiles.find(entry => entry.kind === "source");
    const layoutEntry = result.changedFiles.find(entry => entry.kind === "layout");
    const assetEntry = result.changedFiles.find(entry => entry.kind === "asset");
    const savedSource = decoder.decode(root.read(sourceEntry.path));
    const savedLayout = JSON.parse(decoder.decode(root.read(layoutEntry.path)));
    const savedAsset = root.read(assetEntry.path);
    const verifiedHash = await feature.sha256(encoder.encode(savedSource));

    const conflictRoot = new MemoryDirectoryHandle();
    const externalSource = feature.source.text + "\n外部修改\n";
    conflictRoot.seed(feature.source.name, externalSource);
    let conflictCode = "";
    try {
      await feature.saveToDirectory(conflictRoot);
    } catch (error) {
      conflictCode = error.code;
    }

    const addedLayoutRoot = new MemoryDirectoryHandle();
    addedLayoutRoot.seed(feature.source.name, feature.source.text);
    addedLayoutRoot.seed(feature.layoutName(), "{\"external\":true}\n");
    let addedLayoutConflictCode = "";
    try {
      await feature.saveToDirectory(addedLayoutRoot);
    } catch (error) {
      addedLayoutConflictCode = error.code;
    }

    const removedLayoutRoot = new MemoryDirectoryHandle();
    removedLayoutRoot.seed(feature.source.name, feature.source.text);
    const missingLayoutChangeSet = feature.buildChangeSet();
    missingLayoutChangeSet.base.layoutSha256 = "a".repeat(64);
    let removedLayoutConflictCode = "";
    try {
      await feature.saveToDirectory(removedLayoutRoot, missingLayoutChangeSet);
    } catch (error) {
      removedLayoutConflictCode = error.code;
    }

    return {
      result,
      savedSource,
      savedLayout,
      assetSignature: [...savedAsset.slice(0, 8)],
      verifiedHash,
      conflictCode,
      conflictUnchanged: decoder.decode(conflictRoot.read(feature.source.name)) === externalSource,
      addedLayoutConflictCode,
      addedLayoutUnchanged: decoder.decode(addedLayoutRoot.read(feature.layoutName())) === "{\"external\":true}\n",
      removedLayoutConflictCode
    };
  });

  assert.equal(saveResult.result.status, "saved");
  assert.equal(saveResult.result.needsRebuild, true);
  assert.equal(saveResult.result.sourceSha256, saveResult.verifiedHash);
  assert.equal(saveResult.savedLayout.sourceHash, saveResult.result.sourceSha256);
  assert.equal(saveResult.savedLayout.source, "slides.md");
  assert.equal(saveResult.savedLayout.slides["authoring-target"].layout, "gallery");
  assert.equal(saveResult.savedLayout.slides.P3, undefined);
  assert.deepEqual(saveResult.savedLayout.slides["authoring-target"].regions.content, {x: 140, y: 230, width: 1600, height: 650});
  assert.notDeepEqual(saveResult.savedLayout.slides["authoring-target"].regions.copy, {x: 140, y: 230, width: 1600, height: 650});
  assert.deepEqual(saveResult.savedLayout.slides["authoring-target"].typography, {lineHeight: 1.5, color: "#222222", bold: false});
  assert.match(saveResult.savedSource, /assets\/authoring\/[0-9a-f]{16}-pasted-example\.png/);
  assert.deepEqual(saveResult.assetSignature, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  assert.equal(saveResult.conflictCode, "SOURCE_CONFLICT");
  assert.equal(saveResult.conflictUnchanged, true);
  assert.equal(saveResult.addedLayoutConflictCode, "SOURCE_CONFLICT");
  assert.equal(saveResult.addedLayoutUnchanged, true);
  assert.equal(saveResult.removedLayoutConflictCode, "SOURCE_CONFLICT");

  console.log("Content authoring browser test passed.");
} finally {
  if (browser) await browser.close();
  await rm(outputRoot, {recursive: true, force: true});
}
