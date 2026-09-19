import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {existsSync, mkdirSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import puppeteer from 'puppeteer';

const work = resolve('work/list-hierarchy');
mkdirSync(work,{recursive:true});
const output = resolve(work,'index.html');
execFileSync(process.env.PYTHON || (process.platform==='win32'?'python':'python3'),
  ['-X','utf8','build_slides.py','harnesses/list-hierarchy/slides.md','-o',output,'--strict'],{windowsHide:true});
const executablePath = [process.env.PUPPETEER_EXECUTABLE_PATH,'C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(p=>p&&existsSync(p));
const browser = await puppeteer.launch({headless:true,...(executablePath&&{executablePath})});
try {
  const page = await browser.newPage();
  const errors = [], results = [];
  page.on('pageerror',error=>errors.push(error.message));
  for (const [file, cases] of [
    [output, {'nested-list':[2,1]}],
  ]) {
    await page.goto(pathToFileURL(file).href,{waitUntil:'load'});
    for (const width of [1920,1280]) {
      await page.setViewport({width,height:width*9/16});
      for (const [id,children] of Object.entries(cases)) {
        await page.evaluate(id=>{
          const slides=[...document.querySelectorAll('.slide')];
          window.__SLIDE_PRESENTATION__.show(slides.findIndex(s=>s.dataset.slideId===id),false);
        },id);
        await new Promise(resolve=>setTimeout(resolve,450));
        const result=await page.evaluate(()=>{
          const slide=document.querySelector('.slide.active');
          const listRoot=slide.querySelector('.text-card [data-author-field="body"] > ol')
            || slide.querySelector('.text-card > ol');
          const parents=listRoot ? [...listRoot.children].filter(node=>node.tagName==='LI') : [];
          return {
            id:slide.dataset.slideId,
            children:parents.map(li=>li.querySelector(':scope > ol,:scope > ul')?.children.length||0),
            indented:parents.every(li=>{
              const child=li.querySelector(':scope > ol > li,:scope > ul > li');
              return !child||child.getBoundingClientRect().left>li.getBoundingClientRect().left+10;
            }),
            overflow:[...slide.querySelectorAll('.card')].filter(el=>el.scrollHeight>el.clientHeight+2||el.scrollWidth>el.clientWidth+2).length,
          };
        });
        assert.deepEqual(result.children,children);
        assert(result.indented);
        assert.equal(result.overflow,0);
        results.push({width,...result});
        await page.screenshot({path:resolve(work,`${id}-${width}.png`)});
      }
    }
  }
  assert.deepEqual(errors,[]);
  writeFileSync(resolve(work,'verification.json'),JSON.stringify({results,errors},null,2));
  console.log('List hierarchy: standalone harness nested DOM and visible indentation verified at two widths.');
} finally {await browser.close();}
