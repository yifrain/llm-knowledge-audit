"use strict";
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const state = {lang: localStorage.getItem("llmka.language") || "en", page:"runs", token:"", runs:[], env:null, run:"", detail:null, trace:null, stage:0, caseId:"", scope:"pilot", reviewTab:"gold", queue:null, packet:null, index:0, wizard:null, notice:""};
if (!MESSAGES[state.lang]) state.lang = "en";
const t = key => MESSAGES[state.lang][key] || MESSAGES.en[key] || key;
const text = key => esc(t(key));
const button = (key, action, cls="", extra="") => `<button type="button" class="${cls}" data-action="${action}" ${extra}>${text(key)}</button>`;
const english = html => `<div lang="en">${html}</div>`;
const url = value => { try { const u = new URL(value); return ["https:","http:"].includes(u.protocol) ? esc(u.href) : "#"; } catch { return "#"; } };
const link = (href, label) => `<a href="${url(href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
const field = (key, id, value, type="text", extra="") => `<label>${text(key)}<input id="${id}" type="${type}" value="${esc(value)}" ${extra}></label>`;
const rate = value => value?.value == null ? text("noData") : `${value.numerator} / ${value.denominator} · ${(value.value*100).toFixed(1)}%`;
const stages = ["collect-candidates","disambiguate-string","disambiguate-context","generate-triples","retrieve-evidence","judge","evaluate","build-report"];
function notice(key) { state.notice = key; $("#notice").textContent = key ? t(key) : ""; }
async function api(path, body) {
  let response;
  try { response = await fetch(path, body === undefined ? {cache:"no-store"} : {method:"POST", headers:{"Content-Type":"application/json","X-Review-Token":state.token}, body:JSON.stringify(body)}); }
  catch { throw new Error("network_error"); }
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "invalid_request");
  return value;
}
function applyLanguage() {
  document.documentElement.lang = state.lang;
  document.title = t("title");
  $("#language").value = state.lang;
  $("#language").setAttribute("aria-label",t("language"));
  $("#nav").setAttribute("aria-label",t("console"));
  document.querySelectorAll("[data-i18n]").forEach(el => el.textContent = t(el.dataset.i18n));
  notice(state.notice);
}
function render() {
  const focused = document.activeElement;
  const focusId = focused?.id;
  const focusAction = focused?.dataset?.action;
  applyLanguage();
  document.querySelectorAll("[data-page]").forEach(el => el.setAttribute("aria-current",el.dataset.page === state.page ? "page":"false"));
  $("#main").innerHTML = state.wizard ? wizardView() : ({runs:runsView,inspect:inspectView,review:reviewView,exports:exportsView}[state.page])();
  if (focusId) document.getElementById(focusId)?.focus({preventScroll:true});
  else if (focusAction) [...document.querySelectorAll("main button[data-action]")].find(e => e.dataset.action === focusAction && e.dataset.stage === focused.dataset.stage && e.dataset.run === focused.dataset.run)?.focus({preventScroll:true});
}
function runsTable() {
  if (!state.runs.length) return `<p class="empty">${text("noRuns")}</p>`;
  return `<div class="table-wrap"><table><thead><tr>${["run","mode","status","cases","created"].map(k=>`<th>${text(k)}</th>`).join("")}<th></th></tr></thead><tbody>${state.runs.map(r=>`<tr><td class="identifier">${esc(r.id)}</td><td>${text(r.mode)}</td><td>${text(r.status)}${r.completed_stages != null ? ` · ${r.completed_stages}/8`:""}</td><td>${r.n}</td><td>${esc(new Date(r.created_at).toLocaleString(state.lang))}</td><td>${button("open","open-run","",`data-run="${esc(r.id)}"`)}</td></tr>`).join("")}</tbody></table></div>`;
}
function runsView() { return `<div class="toolbar"><h1>${text("runs")}</h1>${button("newRun","new","primary")}</div><div id="run-list">${runsTable()}</div>`; }
function selectedHeader(key) {
  return `<div class="toolbar"><h1>${text(key)}</h1><label>${text("selectRun")}<select id="select-run"><option value="">—</option>${state.runs.filter(r=>!r.id.startsWith("job/")).map(r=>`<option value="${esc(r.id)}" ${state.run===r.id?"selected":""}>${esc(r.id)}</option>`).join("")}</select></label></div>`;
}
function progressView(p) {
  if (!p) return "";
  return `<div class="rule"><span class="identifier">${esc(p.id)}</span><p>${text(p.status)} · ${p.completed_stages ?? 0}/8 ${text("stages")}</p>${p.mode==="mock"?`<p class="muted">${text("mockNote")}</p>`:""}${p.failure_code || p.code ? `<p>${text(p.failure_code || p.code)} ${esc(p.failure_type || p.type || "")}</p>`:""}${p.failures?.length?`<details><summary>${text("details")}</summary><pre class="identifier" lang="en">${esc(JSON.stringify(p.failures,null,2))}</pre></details>`:""}${p.status==="failed" && !p.id.startsWith("job/") ? button("resume","resume"):""}</div>${p.stages ? `<div class="summary"><div><b>${p.attempts} / ${p.max_calls}</b><small>${text("attempts")}</small></div><div><b>$${p.reserved_usd.toFixed(4)} / $${p.budget_usd.toFixed(2)}</b><small>${text("reserved")}</small></div><div><b>${p.human_verified_cases} / ${p.n}</b><small>${text("gold")} · ${p.human_verified_cases===p.n?text("verified"):text("unverified")}</small></div></div><ol class="stages">${p.stages.map((s,i)=>`<li><button data-action="stage" data-stage="${i}" aria-current="${state.stage===i?"step":"false"}">${i+1}. ${text("s"+i)}<small>${text(s.status)}</small></button></li>`).join("")}</ol>`:""}`;
}
function inspectView() {
  const d = state.detail;
  let html = selectedHeader("inspect");
  if (!d) return html + `<p class="empty">${text("noSelection")}</p>`;
  html += `<div id="progress">${progressView(d.progress)}</div>`;
  if (!d.cases) return html;
  html += `<label>${text("case")}<select id="select-case" lang="en">${d.cases.map(c=>`<option value="${esc(c.case_id)}" ${c.case_id===state.caseId?"selected":""}>${esc(c.surface_form)} · ${esc(c.case_id)}</option>`).join("")}</select></label>`;
  const c = state.trace?.case;
  if (c) html += `<p class="muted">${text("english")} · ${text("snapshot")}</p>${english(`<h2>${esc(c.surface_form)}</h2><p>${esc(c.context)}</p><p>${link(c.source_url,c.gold_label+" · "+c.gold_entity_id)}</p>`)}<p class="status">${c.verification_status==="human_verified"?text("verified"):text("unverified")}</p>`;
  html += `<h2>${state.stage+1}. ${text("s"+state.stage)}</h2><p class="muted">${text("d"+state.stage)}</p>`;
  if (state.stage===0) {
    const rows=d.candidates[state.caseId]?.candidates || [];
    html += rows.length ? english(`<div class="table-wrap"><table><tbody>${rows.map(c=>`<tr><td>${link("https://www.wikidata.org/wiki/"+c.entity_id,c.entity_id)}</td><td>${esc(c.label)}</td><td>${esc(c.description)}</td></tr>`).join("")}</tbody></table></div>`) : `<p>${text("notReady")}</p>`;
  } else if (state.stage<=2) {
    html += `<div class="grid">${["string","context"].map(m=>{const r=d[m][state.caseId];return `<section><h3>${text(m)}</h3>${r?english(`<p>${r.selected_entity_id?link("https://www.wikidata.org/wiki/"+r.selected_entity_id,r.selected_entity_id):text("none")}</p><p>${esc(r.short_rationale || r.error || "")}</p><p>${esc(r.confidence ?? "")}</p>`):text("notReady")}</section>`;}).join("")}</div>`;
  } else if (state.stage<=5) {
    if (!d.blind_complete) html += `<p class="muted">${text("blind")}</p>`;
    html += (state.trace?.claims || []).map(r=>`<article class="claim">${english(`<span class="identifier">${esc(r.triple_id)}</span><p>${triple(r.triple)}</p>`)}${state.stage>=4?evidenceView(r.evidence,false):""}${state.stage===5 && r.judgment ? english(`<pre>${esc(JSON.stringify(r.judgment,null,2))}</pre>`):""}</article>`).join("") || `<p>${text("notReady")}</p>`;
  } else if (state.stage===6) html += resultsView();
  else html += exportList();
  return html;
}
function triple(r) { return [r.subject,r.predicate,r.object].map(esc).join(" → "); }
function evidenceView(rows, check) {
  return (rows||[]).map((e,i)=>`<section class="evidence">${check?`<label><input type="checkbox" name="evidence" value="${esc(e.passage_id)}" ${state.packet?.rows[state.index]?.annotation?.evidence_ids.includes(e.passage_id)?"checked":""}> <span lang="en">${esc(e.passage_id)}</span></label>`:""}${english(`<p>${esc(e.text)}</p><small>${link(e.source_url,e.passage_id)} · ${esc(e.license)} · ${esc(e.revision_id || e.retrieved_at)}</small>`)}</section>`).join("") || `<p>${text("noData")}</p>`;
}
function resultsView() {
  const d=state.detail, m=d.metrics;
  if (!m?.entity) return `<p>${text("notReady")}</p>`;
  return `<div class="summary">${["string","context"].map(k=>`<div><b>${rate(m.entity[k].top1_accuracy)}</b><small>${text(k)} · ${text("accuracy")}</small></div>`).join("")}<div><b>${rate(m.candidates.recall_at_k)}</b><small>${text("recall")}</small></div></div>${!d.blind_complete?`<p class="muted">${text("blind")}</p>`:`<h3>${text("comparison")}</h3><pre class="identifier" lang="en">${esc(JSON.stringify(d.comparison,null,2))}</pre>`}<details><summary>${text("details")}</summary><pre class="identifier" lang="en">${esc(JSON.stringify(m,null,2))}</pre></details>`;
}
function exportsView() { return selectedHeader("exports") + (state.detail?.cases ? exportList() : `<p class="empty">${text("noSelection")}</p>`); }
function exportList() {
  const d=state.detail;
  if (!d) return "";
  const files=[["summary.json","summaryExport",false],["manifest.json","manifestExport",false],["cases.json","casesExport",false],["annotation_packet.json","packetExport",false],["report.md","reportExport",true],["evaluate.json","metricsExport",true],["review-comparison.json","comparisonExport",true],["figures.zip","figuresExport",true]];
  return `<p class="muted">${text("exportNote")}</p>${!d.blind_complete?`<p>${text("blind")}</p>`:""}<table><tbody>${files.filter(f=>!(f[0]==="figures.zip"&&d.progress.mode==="mock")).map(([name,key,gated])=>`<tr><td>${text(key)}<br><span class="identifier">${name}</span></td><td>${gated&&!d.blind_complete ? text("locked"):button("download","download","",`data-name="${name}"`)}</td></tr>`).join("")}</tbody></table>`;
}
function reviewView() {
  let html=selectedHeader("review")+`<div class="actions rule">${button("goldReview","review-gold")}${button("factReview","review-facts")}</div>`;
  if(state.reviewTab==="gold") return html+goldView();
  if (!state.run || state.run.startsWith("job/")) return html+`<p>${text("noSelection")}</p>`;
  if(state.run.startsWith("mock/")) return html+`<p>${text("mockReview")}</p>`;
  const packet=state.packet;
  if(!packet) return html+`<p>${text("notReady")}</p>`;
  html+=`<p>${text("factOptional")}</p><p>${text("reviewed")}: ${packet.completed} / ${packet.sample_size} · ${text("population")}: ${packet.population_size}</p>`;
  const r=packet.rows[state.index];
  if(!r) return html+`<p>${text("noData")}</p>`;
  const annotation=r.annotation;
  return html+`<article class="claim"><p>${state.index+1} / ${packet.sample_size} · ${text("english")}</p>${english(`<span class="identifier">${esc(r.triple_id)}</span><h2>${triple(r.triple)}</h2>`)}${button("copy","copy")}<p>${text("citeInstruction")}</p>${evidenceView(r.evidence,true)}<fieldset><legend>${text("factReview")}</legend>${["entailed","contradicted","not_enough_information"].map(k=>`<label class="checkline"><input type="radio" name="human-label" value="${k}" ${annotation?.human_label===k?"checked":""}> ${text(k)}</label>`).join("")}</fieldset>${field("reviewer","annotator",annotation?.annotator_id || localStorage.getItem("llmka.reviewer") || "")}<label>${text("notes")}<textarea id="notes" rows="2">${esc(annotation?.annotator_notes || "")}</textarea></label><div class="actions">${button("prev","prev","",state.index===0?"disabled":"")}${button("saveAnnotation","annotate","primary")}${button("skip","next-fact","",state.index===packet.sample_size-1?"disabled":"")}</div></article>`;
}
function goldView() {
  const q=state.queue;
  let html=`<label>${text("scope")}<select id="scope"><option value="pilot" ${state.scope==="pilot"?"selected":""}>${text("pilot")}</option><option value="starter" ${state.scope==="starter"?"selected":""}>${text("starter")}</option></select></label>`;
  if(!q) return html;
  html+=`<p>${text("goldInstruction")}</p><p>${q.reviewed} / ${q.rows.length} ${text("confirmed")}</p><label class="checkline"><input type="checkbox" id="all-cases"> ${text("selectAll")}</label><div class="table-wrap"><table><thead><tr><th></th><th>${text("case")}</th><th>${text("gold")}</th><th>${text("source")}</th></tr></thead><tbody>${q.rows.map((c,i)=>`<tr><td><input type="checkbox" name="case-review" value="${i}" aria-label="${esc(c.case_id)}"></td><td class="case-source" lang="en"><b>${esc(c.surface_form)}</b><p>${esc(c.context)}</p><small>${esc(c.case_id)}</small></td><td class="case-source"><div lang="en">${link("https://www.wikidata.org/wiki/"+c.gold_entity_id,c.gold_label+" · "+c.gold_entity_id)}<p>${esc(c.gold_description)}</p></div><small>${c.verification_status==="human_verified"?text("verified"):text("unverified")}</small><details><summary>${text("override")}</summary>${[["goldId","gold_entity_id"],["goldLabel","gold_label"],["description","gold_description"],["sourceURL","source_url"]].map(([key,name])=>field(key,`case-${i}-${name}`,c[name])).join("")}</details></td><td>${link(c.source_url,t("source"))}</td></tr>`).join("")}</tbody></table></div><p class="muted">${text("batchNote")}</p>${field("reviewer","gold-reviewer",localStorage.getItem("llmka.reviewer") || "")}<label class="checkline"><input type="checkbox" id="confirm-batch"> ${text("confirmBatch")}</label>${button("batchSave","batch","primary")}`;
  return html;
}
function wizardView() {
  const w=state.wizard, b=w.body, p=w.preview;
  const labels=["dataset","limits","models","credentials","approval"];
  // 环境里是否已有可用凭据（决定「使用 .env」按钮是否可点）
  const ambient=["resolver","generator","judge"].some(r=>p?.env_keys_available?.[r]);
  let html=`<div class="wizard"><div class="toolbar"><h1>${text(w.resume?"resume":"newRun")}</h1>${button("cancel","cancel")}</div><ol class="wizard-steps">${labels.map((key,i)=>`<li aria-current="${i===w.step?"step":"false"}">${i+1}. ${text(key)}</li>`).join("")}</ol>`;
  if(w.resume) html+=`<p class="identifier">${esc(w.resume)}</p>`;
  if(w.step===0) html+=`<fieldset><legend>${text("mode")}</legend><label class="checkline"><input name="mode" type="radio" value="real" ${b.mode==="real"?"checked":""}> ${text("real")}</label><label class="checkline"><input name="mode" type="radio" value="mock" ${b.mode==="mock"?"checked":""}> ${text("mock")}</label></fieldset><div class="fields"><label>${text("dataset")}<select id="dataset"><option value="pilot" ${b.dataset==="pilot"?"selected":""}>${text("pilot")}</option><option value="starter" ${b.dataset==="starter"?"selected":""}>${text("starter")}</option></select></label>${field("caseLimit","case-limit",b.case_limit,"number",'min="1" max="12"')}</div><label class="checkline"><input id="gold-required" type="checkbox" ${b.require_human_verified?"checked":""}> ${text("goldRequired")}</label><p class="muted">${text("goldOptional")}</p>`;
  if(w.step===1) html+=`${b.mode==="mock"?`<p>${text("mockNote")} ${text("offlineFree")}</p>`:""}<div class="fields">${field("budget","budget",b.budget_usd,"number",'min="0.01" max="10" step="0.01"')}${field("attemptCap","max-calls",b.max_calls,"number",'min="1"')}${field("triplesLimit","triples-limit",b.triples_per_entity,"number",'min="1" max="15"')}</div>${planSummary(p)}<p class="muted">${text("costNote")}</p>`;
  if(w.step===2) html+= b.mode==="mock" ? `<p>${text("mockNote")}</p>` : `<p class="muted">${text("priceNote")}</p>${["resolver","generator","judge"].map(role=>`<section class="model"><h2>${text(role)}</h2><div class="grid">${field("model",role+"-model",b.models[role].model)}${field("endpoint",role+"-base_url",b.models[role].base_url,"url")}</div><div class="fields">${field("inputPrice",role+"-input_usd_per_million",b.models[role].input_usd_per_million,"number",'min="0.00001" step="any"')}${field("outputPrice",role+"-output_usd_per_million",b.models[role].output_usd_per_million,"number",'min="0.00001" step="any"')}${field("outputTokens",role+"-max_output_tokens",b.models[role].max_output_tokens,"number",'min="100" max="8000"')}</div></section>`).join("")}`;
  if(w.step===3) html+= b.mode==="mock"?`<p>${text("mockNote")}</p>`:`<p>${text("keyNotice")}</p><section class="model"><h3>${text("envTitle")}</h3><p class="identifier" lang="en">${state.env?.path?esc(state.env.path):text("envNone")}</p>${state.env?.names?.length?`<p class="muted" lang="en">${esc(state.env.names.join(", "))}</p>`:""}<p class="muted">${text("envHint")}</p><div class="actions">${button("useEnv","use-env","",ambient?"":"disabled")}</div></section><p class="muted">${text("keyShared")}</p>${["resolver","generator","judge"].map(role=>`<section class="model"><h3>${text(role)}</h3><p class="identifier" lang="en">${esc(p.models[role].base_url)} · ${esc(p.models[role].model)}</p>${field("key",role+"-key","","password",'autocomplete="off" spellcheck="false"')}<small>${p.credentials_ready[role]?text("ready"):text("missing")}</small> <small>${p.env_keys_available?.[role]?text("envAvailable"):text("envMissing")}</small></section>`).join("")}<div class="actions">${button("saveKeys","keys")}${button("clearKeys","clear-keys")}</div>`;
  if(w.step===4) html+=`${planSummary(p)}<div class="table-wrap"><table><tbody>${Object.entries(p.models).map(([role,m])=>`<tr><td>${text(role)}</td><td lang="en">${esc(m.model)}<br>${p.mode==="real"?esc(m.base_url):""}</td><td>${m.input_usd_per_million} / ${m.output_usd_per_million} USD / 1M</td></tr>`).join("")}</tbody></table></div><p>${p.cases.length-p.pending_review} / ${p.cases.length} · ${text("verified")}</p><p>${text("approvalNote")}</p>${b.mode==="real"?`<label class="checkline"><input id="approve-paid" type="checkbox"> ${text("approve")}</label>`:`<p>${text("mockNote")}</p>`}`;
  html+=`<div class="actions">${w.step>0&&!w.resume?button("back","wizard-back"):""}${w.step<4?button("next","wizard-next","primary"):button(b.mode==="mock"?"startMock":"start","start","primary")}</div></div>`;
  return html;
}
function planSummary(p) {
  if(!p) return "";
  return `<div class="summary"><div><b>${p.cases.length}</b><small>${text("cases")}</small></div><div><b>${p.max_logical_calls}</b><small>${text("logical")}</small></div><div><b>${p.max_http_attempts}</b><small>${text("attemptCap")}</small></div><div><b>$${p.budget_cap_usd}</b><small>${text("budget")}</small></div></div>${p.resume?`<p>${text("inherited")}: ${p.inherited_attempts} · $${p.inherited_reserved_usd.toFixed(4)}</p>`:""}`;
}
function readWizard() {
  const w=state.wizard,b=w.body;
  if(w.resume) return;
  if(w.step===0) Object.assign(b,{mode:$("[name=mode]:checked").value,dataset:$("#dataset").value,case_limit:Number($("#case-limit").value),require_human_verified:$("#gold-required").checked});
  if(w.step===1) Object.assign(b,{budget_usd:Number($("#budget").value),max_calls:Number($("#max-calls").value),triples_per_entity:Number($("#triples-limit").value)});
  if(w.step===2&&b.mode==="real") for(const role of ["resolver","generator","judge"]) for(const key of ["model","base_url","input_usd_per_million","output_usd_per_million","max_output_tokens"]) b.models[role][key]=["model","base_url"].includes(key)?$("#"+role+"-"+key).value.trim():Number($("#"+role+"-"+key).value);
}
async function refreshRuns() { const data=await api("/api/state"); state.token=data.token; state.runs=data.runs; state.env=data.env??null; }
async function openRun(run) {
  state.run=run;
  const p=await api("/api/progress?run="+encodeURIComponent(run));
  if(p.id.startsWith("job/")) { state.detail={progress:p}; state.trace=null; return; }
  state.run=p.id;
  state.detail=await api("/api/run?run="+encodeURIComponent(state.run));
  if(!state.detail.cases.some(c=>c.case_id===state.caseId)) state.caseId=state.detail.cases[0]?.case_id || "";
  state.trace=state.caseId?await api("/api/trace?run="+encodeURIComponent(state.run)+"&case="+encodeURIComponent(state.caseId)):null;
}
async function loadReview() {
  state.queue=await api("/api/cases?scope="+state.scope);
  state.packet=null;
  if(state.run.startsWith("real/")&&state.detail?.progress.completed_stages>=6) state.packet=await api("/api/review?run="+encodeURIComponent(state.run));
}
async function makeWizard(resume) {
  const defaults=await api("/api/defaults"), models={};
  for(const [r,m] of Object.entries(defaults.models)) models[r]=Object.fromEntries(["model","base_url","input_usd_per_million","output_usd_per_million","max_output_tokens"].map(k=>[k,m[k]]));
  state.wizard={step:0,body:{mode:"real",dataset:"pilot",case_limit:5,require_human_verified:false,budget_usd:defaults.budget_usd,max_calls:defaults.max_calls,triples_per_entity:defaults.triples_per_entity,models}};
  if(resume) { const p=await api("/api/preview",{resume}); Object.assign(state.wizard,{resume,step:3,preview:p}); state.wizard.body.mode=p.mode; }
}
async function saveKeys(clear=false) {
  const keys={};
  for(const r of ["resolver","generator","judge"]) keys[r]=clear?"":$("#"+r+"-key").value;
  try { const output=await api("/api/credentials",{plan:state.wizard.preview.plan,keys,clear}); state.wizard.preview.credentials_ready=output.ready; }
  finally { for(const r of Object.keys(keys)) { keys[r]=""; $("#"+r+"-key").value=""; } }
}
async function action(name, el) {
  notice("");
  if(name==="new") await makeWizard();
  if(name==="cancel") state.wizard=null;
  if(name==="open-run") { state.page="inspect"; await openRun(el.dataset.run); }
  if(name==="resume") await makeWizard(state.run);
  if(name==="stage") state.stage=Number(el.dataset.stage);
  if(name==="wizard-back") { readWizard(); state.wizard.step--; }
  if(name==="wizard-next") {
    const w=state.wizard;
    readWizard();
    if(w.step===3&&w.body.mode==="real") await saveKeys();
    if(w.step<3) w.preview=await api("/api/preview",w.body);
    w.step++;
  }
  if(name==="keys"||name==="clear-keys") { await saveKeys(name==="clear-keys"); notice("saved"); }
  if(name==="use-env") {
    // 显式确认：服务端把进程环境里的密钥复制到本 plan 的密钥名下，值不回传浏览器
    const output=await api("/api/credentials",{plan:state.wizard.preview.plan,use_env:true});
    state.wizard.preview.credentials_ready=output.ready; notice("envApplied");
  }
  if(name==="start") {
    const w=state.wizard;
    const result=await api("/api/start",{plan:w.preview.plan,approve_paid:$("#approve-paid")?.checked===true});
    state.wizard=null; state.page="inspect"; await refreshRuns(); await openRun(result.run);
  }
  if(name==="review-gold"||name==="review-facts") { state.reviewTab=name==="review-gold"?"gold":"facts"; await loadReview(); }
  if(name==="batch") {
    const reviewer=$("#gold-reviewer").value.trim();
    const rows=[...document.querySelectorAll('[name="case-review"]:checked')].map(input=>{
      const i=Number(input.value),c=state.queue.rows[i],overrides={};
      for(const k of ["gold_entity_id","gold_label","gold_description","source_url"]) if($("#case-"+i+"-"+k).value!==c[k]) overrides[k]=$("#case-"+i+"-"+k).value;
      return {case_id:c.case_id,revision:c.revision,overrides};
    });
    await api("/api/verify-batch",{scope:state.scope,reviewer,confirmed:$("#confirm-batch").checked,rows});
    localStorage.setItem("llmka.reviewer",reviewer); await loadReview(); notice("saved");
  }
  if(name==="prev") state.index=Math.max(0,state.index-1);
  if(name==="next-fact") state.index=Math.min(state.packet.rows.length-1,state.index+1);
  if(name==="annotate") {
    const label=$("[name=human-label]:checked")?.value,reviewer=$("#annotator").value.trim();
    const ids=[...document.querySelectorAll('[name="evidence"]:checked')].map(e=>e.value);
    if(!label) throw new Error("label_required");
    if(label!=="not_enough_information"&&!ids.length) throw new Error("invalid_evidence");
    await api("/api/annotate",{run:state.run,triple_id:state.packet.rows[state.index].triple_id,human_label:label,evidence_ids:ids,annotator_id:reviewer,annotator_notes:$("#notes").value});
    localStorage.setItem("llmka.reviewer",reviewer); await loadReview(); await openRun(state.run); notice("saved");
  }
  if(name==="copy") { const r=state.packet.rows[state.index]; await navigator.clipboard.writeText(JSON.stringify({triple:r.triple,evidence:r.evidence},null,2)); notice("copied"); return; }
  if(name==="download") {
    const response=await fetch("/api/export?run="+encodeURIComponent(state.run)+"&name="+encodeURIComponent(el.dataset.name));
    if(!response.ok) throw new Error((await response.json()).error);
    const href=URL.createObjectURL(await response.blob()),a=document.createElement("a"); a.href=href; a.download=el.dataset.name; a.click(); setTimeout(()=>URL.revokeObjectURL(href),1000); return;
  }
  render();
}
document.addEventListener("click",async event=>{
  const el=event.target.closest("button"); if(!el) return;
  try {
    el.disabled=true;
    if(el.dataset.page) { state.page=el.dataset.page; state.wizard=null; notice(""); if(state.page==="review") await loadReview(); render(); }
    else if(el.dataset.action) await action(el.dataset.action,el);
  } catch(error) { notice(MESSAGES.en[error.message]?error.message:"invalid_request"); }
  finally { el.disabled=false; }
});
document.addEventListener("change",async event=>{
  const el=event.target;
  try {
    if(el.id==="language") {
      // Preserve unsaved research form inputs on language change; credentials stay only in DOM.
      if(state.wizard) readWizard();
      const controls=[...document.querySelectorAll("main input, main textarea, main select")].map(e=>({id:e.id,name:e.name,value:e.value,checked:e.checked}));
      state.lang=el.value; localStorage.setItem("llmka.language",state.lang); render();
      for(const saved of controls) {
        const nodes=saved.id?[document.getElementById(saved.id)]:[...document.getElementsByName(saved.name)].filter(e=>e.value===saved.value);
        for(const node of nodes.filter(Boolean)) { node.value=saved.value; node.checked=saved.checked; }
      }
    }
    if(el.id==="select-run") { if(el.value) await openRun(el.value); else {state.run="";state.detail=null;} if(state.page==="review") await loadReview(); render(); }
    if(el.id==="select-case") { state.caseId=el.value; await openRun(state.run); render(); }
    if(el.id==="scope") { state.scope=el.value; await loadReview(); render(); }
    if(el.id==="all-cases") document.querySelectorAll('[name="case-review"]').forEach(input=>input.checked=el.checked);
    if(el.id==="dataset") $("#case-limit").value=el.value==="pilot"?5:12;
    if(["budget","max-calls","triples-limit"].includes(el.id) && state.wizard) {
      readWizard(); state.wizard.preview=await api("/api/preview",state.wizard.body); render();
    }
  } catch(error) { notice(MESSAGES.en[error.message]?error.message:"invalid_request"); }
});
async function poll() {
  try {
    const previousRuns=JSON.stringify(state.runs);
    await refreshRuns();
    if(state.page==="runs"&&!state.wizard && previousRuns!==JSON.stringify(state.runs)) render();
    if(state.run && state.detail?.progress.status==="running" && !state.wizard) {
      const before=JSON.stringify(state.detail.progress); await openRun(state.run);
      if(state.page==="inspect"&&before!==JSON.stringify(state.detail.progress)) render();
    }
  } catch { /* Transient polling failures do not discard edits or repeatedly announce errors. */ }
  setTimeout(poll,2000);
}
(async()=>{ try { await refreshRuns(); render(); poll(); } catch(error) {render();notice(error.message);} })();
