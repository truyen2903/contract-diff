const { chromium } = require(process.env.CONTRACTDIFF_PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const assert = require('node:assert/strict');
const { createHash }=require('node:crypto');
const { pathToFileURL }=require('node:url');
(async () => {
 const dir = await fs.mkdtemp(path.join(os.tmpdir(),'contractdiff-playwright-m7-'));
 const browser=await chromium.launch({channel:'chrome',headless:true,timeout:15000,chromiumSandbox:true,args:['--disable-gpu','--disable-software-rasterizer']});
 console.log('Chromium '+browser.version());
 try {
 const context=await browser.newContext({acceptDownloads:true,viewport:{width:1440,height:900}});
 const page=await context.newPage();
 page.setDefaultTimeout(12000);
 await page.goto(process.env.CONTRACTDIFF_DEMO_URL || 'http://127.0.0.1:15171/');
 await page.getByRole('button',{name:'Tạo lần so sánh mới'}).click();
 await page.getByRole('tab',{name:'PDF kỹ thuật số'}).click();
 for (const [i,name] of ['contract_old.pdf','contract_new.pdf'].entries()){
  const bytes=[...await fs.readFile(path.resolve('tests/fixtures',name))];
  const result=await page.locator('.file-drop-inner').nth(i).evaluate((el,{bytes,name})=>{
    const transfer=new DataTransfer();
    transfer.items.add(new File([new Uint8Array(bytes)],name,{type:'application/pdf'}));
    const dragover=new DragEvent('dragover',{bubbles:true,cancelable:true,dataTransfer:transfer});
    el.dispatchEvent(dragover);
    const drop=new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer});
    el.dispatchEvent(drop);
    return {isTrusted:drop.isTrusted,dragoverPrevented:dragover.defaultPrevented,dropPrevented:drop.defaultPrevented};
  },{bytes,name});
  assert.deepEqual(result,{isTrusted:false,dragoverPrevented:true,dropPrevented:true});
  await page.locator('.file-drop-inner').nth(i).getByText(name).waitFor();
 }
 const pdfResponse=page.waitForResponse(r=>r.url().endsWith('/structured/pdf'),{timeout:35000});
 await page.getByRole('button',{name:'Phân tích phiên bản'}).click();
 assert.equal((await pdfResponse).status(),200);
 await page.getByRole('heading',{name:'Kết quả phân tích'}).waitFor();
 assert.match(await page.locator('main').innerText(),/PDF kỹ thuật số · 10 nút cấu trúc/);
 assert.match(await page.locator('main').innerText(),/Trang 1/);
 const widths=[];
 for (const [width,height] of [[1440,900],[1024,768],[768,1024],[390,844],[320,568]]) {
  await page.setViewportSize({width,height});
  const metrics=await page.evaluate(()=>({innerWidth,body:document.body.scrollWidth,root:document.documentElement.scrollWidth,over:[...document.querySelectorAll('main button, main article')].filter(e=>e.getClientRects().length).filter(e=>{const r=e.getBoundingClientRect();return r.left<0||r.right>innerWidth;}).map(e=>e.className)}));
  assert.ok(metrics.root<=width && metrics.body<=width && !metrics.over.length);
  widths.push(metrics);
 }
 await page.setViewportSize({width:1440,height:900});
 console.log('PDF viewport metrics '+JSON.stringify(widths));
 console.log('VERIFIED_BROWSER_SYNTHETIC_EVENT: PDF DataTransfer drop to both slots, HTTP 200, 10 structural nodes, Trang 1.');
 async function exportReport(label){
  let dialogText;
  page.once('dialog',async d=>{dialogText=d.message();await d.accept();});
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Xuất báo cáo'}).click()]);
  const destination=path.join(dir,label+'-'+download.suggestedFilename());
  await download.saveAs(destination);
  const raw=await fs.readFile(destination);
  const html=new TextDecoder('utf-8',{fatal:true}).decode(raw);
  assert.match(dialogText,/Bạn có muốn tải xuống không/);
  assert.match(html,/Báo cáo so sánh/);
  assert.match(html,/Phiên bản cũ · Trang 1/);
  assert.match(html,/Phiên bản mới · Trang 1/);
  assert.match(html,/default-src 'none'; style-src 'unsafe-inline'/);
  assert.doesNotMatch(html,/<script\b|<(?:link|iframe|img)\b|\s(?:src|href)=/i);
  const reportContext=await browser.newContext({offline:true});
  try {
   const reportPage=await reportContext.newPage();
   const external=[];
   reportPage.on('request', request => { if (/^https?:/.test(request.url())) external.push(request.url()); });
   await reportPage.goto(pathToFileURL(destination).href);
   await reportPage.getByRole('heading',{name:'ContractDiff · Báo cáo so sánh'}).waitFor();
   assert.equal(external.length,0);
  } finally { await reportContext.close(); }
  console.log(label,JSON.stringify({destination,bytes:raw.length,sha256:createHash('sha256').update(raw).digest('hex')}));
  return html;
 }
 const pdfHtml=await exportReport('pdf');
 assert.match(pdfHtml,/12[.,]?000[.,]?000/);
 assert.match(pdfHtml,/15[.,]?000[.,]?000/);
 assert.match(pdfHtml,/MONEY_CHANGE/);
 const priorities=[...new Set([...pdfHtml.matchAll(/<\/strong> · (LOW|MEDIUM|HIGH|CRITICAL)/g)].map(m=>m[1]))];
 assert.ok(priorities.length);
 console.log('PDF export priorities: '+priorities.join(', '));
 await page.getByRole('button',{name:'So sánh khác'}).click();
 for(const [i,value] of ['100.000.000','120.000.000'].entries()) {
  await page.locator('textarea').nth(i).fill('ĐIỀU 1. Giá trị hợp đồng là '+value+' đồng. Dữ liệu minh họa <b>kiểm tra</b>.');
 }
 const textResponse=page.waitForResponse(r=>r.url().endsWith('/structured/text'),{timeout:35000});
 await page.getByRole('button',{name:'Phân tích phiên bản'}).click();
 assert.equal((await textResponse).status(),200);
 await page.getByRole('heading',{name:'Kết quả phân tích'}).waitFor();
 const textHtml=await exportReport('text');
 assert.match(textHtml,/&lt;b&gt;kiểm tra&lt;\/b&gt;/);
 assert.doesNotMatch(textHtml,/<b>kiểm tra<\/b>/);
 assert.match(textHtml,/CRITICAL/);
 console.log('VERIFIED_REAL_BROWSER: two downloads with valid UTF-8, both comparison versions, review priorities, sources, restrictive CSP, no script elements/external resources, literal markup escaped.');
 } finally { await browser.close(); }
})().catch(err=>{console.error(err);process.exitCode=1;});
