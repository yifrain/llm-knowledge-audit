// No packages, browser process, sockets, or external resources required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assets = path.resolve(__dirname, '../../src/llm_knowledge_audit/workbench/assets');
const handlers = {};
const elements = Object.fromEntries(['main','language','nav','notice','run-list'].map(id=>[id,{value:'en',innerHTML:'',textContent:'',setAttribute(){}}]));
const document = {
  documentElement: {lang:'en'}, title:'',
  querySelector(selector) { return elements[selector.slice(1)]; },
  querySelectorAll() { return []; },
  addEventListener(event, handler) { handlers[event] = handler; },
};
const context = vm.createContext({document, localStorage:{getItem(){return null;},setItem(){}},
  fetch:async()=>({ok:true,json:async()=>({runs:[],token:'test-token'})}),
  setTimeout(){}, URL, console});
vm.runInContext(fs.readFileSync(path.join(assets,'i18n.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(assets,'app.js'),'utf8'),context);
(async()=>{
  // Let initial async render finish.
  await new Promise(setImmediate);
  assert.equal(document.documentElement.lang,'en');
  assert.match(elements.main.innerHTML,/New run/);
  assert.doesNotMatch(elements.main.innerHTML,/[\u3400-\u9fff]/);
  assert.match(fs.readFileSync(path.join(assets,'index.html'),'utf8'),/id="language"/);
  assert.deepEqual(vm.runInContext('Object.keys(MESSAGES.en).sort()',context),vm.runInContext('Object.keys(MESSAGES["zh-CN"]).sort()',context));
  await handlers.change({target:{id:'language',value:'zh-CN'}});
  assert.equal(document.documentElement.lang,'zh-CN');
  assert.match(document.title,/研究控制台/);
  assert.match(elements.main.innerHTML,/新建运行/);
  await handlers.change({target:{id:'language',value:'en'}});
  assert.equal(document.title,'Knowledge audit · Research console');
  assert.doesNotMatch(elements.main.innerHTML,/[\u3400-\u9fff]/);
  assert.match(vm.runInContext('english("evidence")',context),/lang="en"/);
  console.log('Frontend smoke passed: English default, live language/title switch, message parity, data language.');
})().catch(error=>{ console.error(error); process.exitCode=1; });
