import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {existsSync, mkdirSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import puppeteer from 'puppeteer';

// Rebuild from the checked-in cloud snapshot. Tests never need login/network.
const work = resolve('work/lark-browser');
mkdirSync(work, {recursive:true});
// Keep the verification build beside the checked-in artifact because the
// static-export manifest stores asset paths relative to the output directory.
const output = resolve('examples/lark/.verification-index.html');
const report = resolve('examples/lark/.verification-index.build.json');
execFileSync(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'), ['-X', 'utf8', '-c', `
from pathlib import Path
import build_slides
from src.importers.lark import embed_media
source = Path('examples/lark/index.lark/slides.md').resolve()
output = Path(${JSON.stringify(output)})
assert build_slides.build(source, output, strict=True) == 0
embed_media(output, source.parent)
`], {windowsHide:true});
const generated = readFileSync(output,'utf8').replace(
  'this.htmlOutputName = ".verification-index.html";',
  'this.htmlOutputName = "index.html";',
);
assert.equal(generated,readFileSync('examples/lark/index.html','utf8'),'generated Lark example must match current sources');
const executablePath = [process.env.PUPPETEER_EXECUTABLE_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(p => p && existsSync(p));
const browser = await puppeteer.launch({headless:true, ...(executablePath && {executablePath})});
try {
  const page = await browser.newPage();
  const requests = [], errors = [], results = [];
  page.on('request', request => {if (/^https?:/.test(request.url())) requests.push(request.url());});
  page.on('pageerror', error => errors.push(error.message));
  await page.setOfflineMode(true);
  await page.setViewport({width:1920,height:1080,deviceScaleFactor:1});
  await page.goto(pathToFileURL(output).href, {waitUntil:'load'});
  const count = await page.$$eval('.slide', slides => slides.length);
  assert.equal(count, 8);
  for (const width of [1920,1280]) {
    await page.setViewport({width,height:1080});
    for (let index = 0; index < count; index++) {
      await page.evaluate(index => window.__SLIDE_PRESENTATION__.show(index,false),index);
      await new Promise(resolve => setTimeout(resolve,450));
      const result = await page.evaluate(() => {
        const slide = document.querySelector('.slide.active');
        return {
          id:slide.dataset.slideId,
          layout:slide.dataset.layoutResolved,
          images:[...slide.querySelectorAll('img')]
            .filter(img => !img.closest('[data-global-logo]'))
            .map(img => ({loaded:img.complete && img.naturalWidth>0, embedded:img.src.startsWith('data:image/')})),
          overflow:[...slide.querySelectorAll('.text-card,.table-card,.code-card')].filter(el => el.scrollHeight>el.clientHeight+2 || el.scrollWidth>el.clientWidth+2).map(el => el.className),
        };
      });
      assert.deepEqual(result.overflow, [], `${width}: ${result.id}`);
      assert(result.images.every(img => img.loaded && img.embedded));
      results.push({width,...result});
      if (width===1920) await page.screenshot({path:resolve(work,`page-${index+1}.png`)});
    }
  }
  assert.equal(await page.$$eval('.slide[data-slide-id="table-controls"] tbody tr', rows => rows.length),5);
  assert.equal(await page.$$eval('.slide[data-slide-id="chart-controls"] svg', nodes => nodes.length),1);
  assert.equal(await page.$$eval('.slide[data-slide-id="square-image"] mark', nodes => nodes.length),1);
  assert.equal(await page.$$eval('.slide[data-slide-id="chinese-layout"] .callout-tip', nodes => nodes.length),1);
  assert.deepEqual(errors,[]);
  assert.deepEqual(requests,[]);
  const diagnostics = await page.evaluate(() => window.__SLIDE_DIAGNOSTICS__);
  assert.deepEqual(diagnostics.issues,[]);
  writeFileSync(resolve(work,'verification.json'), JSON.stringify({pages:count,results,diagnostics,errors,requests},null,2));
  console.log('Lark import: 8 pages, 2 viewports, offline images/table/chart/highlight/callout verified.');
} finally {
  await browser.close();
  rmSync(output, {force:true});
  rmSync(report, {force:true});
}
