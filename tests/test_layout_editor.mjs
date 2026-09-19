import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {existsSync, mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import puppeteer from 'puppeteer';

mkdirSync('work/layout-editor', {recursive:true});
const output = resolve('work/layout-editor/index.html');
execFileSync('python', ['build_slides.py', 'harnesses/layout-editor/slides.md', '-o', output, '--strict']);
const executablePath = [process.env.PUPPETEER_EXECUTABLE_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(p => p && existsSync(p));
const browser = await puppeteer.launch({headless:true, ...(executablePath && {executablePath})});
try {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(process.env.LAYOUT_EDITOR_DECK ? resolve(process.env.LAYOUT_EDITOR_DECK) : output).href);
  for (const width of [1920, 1280]) {
    await page.setViewport({width, height:1080});
    for (const index of [0, 1]) {
      await page.evaluate(index => {
        const p = window.__SLIDE_PRESENTATION__;
        p.show(index, false);
        p.layoutEditor.setActive(true);
      }, index);
      await new Promise(resolve => setTimeout(resolve, 800));
      const result = await page.evaluate(() => {
        const p = window.__SLIDE_PRESENTATION__, e = p.layoutEditor, s = e.currentSlide();
        const parts = e.actualParts(s);
        const errors = [];
        for (const name of ['visual', 'copy']) {
          if (!parts[name]) continue;
          const a = parts[name].getBoundingClientRect();
          const b = s.querySelector(`.layout-region-box[data-region="${name}"]`).getBoundingClientRect();
          for (const key of ['x','y','width','height']) if (Math.abs(a[key]-b[key]) > 2) errors.push(`${name}.${key}: ${a[key]} != ${b[key]}`);
        }
        const option = getComputedStyle(document.querySelector('#editorLayout option:last-child'));
        return {errors, color:option.color, background:option.backgroundColor, saved:Object.keys(e.entries)};
      });
      assert.deepEqual(result.errors, []);
      assert.notEqual(result.color, result.background);
      assert.equal(result.background, 'rgb(37, 35, 45)');
      assert.deepEqual(result.saved, [], 'opening editor must not persist overrides');
    }
  }
  await page.evaluate(() => {
    const p = window.__SLIDE_PRESENTATION__;
    p.show(0, false);
  });
  await new Promise(resolve => setTimeout(resolve, 800));
  await page.screenshot({path:'work/layout-editor/verified.png'});
  await page.evaluate(() => {
    const p = window.__SLIDE_PRESENTATION__;
    p.layoutEditor.changeLayout('hero-reverse');
  });
  const saved = await page.evaluate(() => window.__SLIDE_PRESENTATION__.layoutEditor.exportPayload());
  await page.reload();
  assert.deepEqual(await page.evaluate(() => window.__SLIDE_PRESENTATION__.layoutEditor.exportPayload()), saved,
    'explicit layout changes must survive reload');
  console.log('Layout editor: native option colors and actual bounds verified at two viewport sizes.');
} finally { await browser.close(); }
