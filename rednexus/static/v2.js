'use strict';
// V2 studio panels reuse the existing in-memory session and server authorization.
async function api2(path, options={}) {
  const response = await fetch('/v2'+path, {...options, headers:{'Content-Type':'application/json',
    Authorization:'Bearer '+token, ...options.headers}});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
  return data;
}
for (const [name,label] of [['workflow','Workflow builder'],['templates','Templates'],['discovery','Service status'],
  ['groups','Agent teams'],['semantic','Semantic memory'],['operations','Operations']]) {
  const button=document.createElement('button');button.dataset.page=name;button.textContent=label;$('nav').append(button);
}
$('.release').textContent='PLATFORM PREVIEW · 2.0.0 RC1';
$('.sidebar-footer small').textContent='v2.0.0 RC1 · Validation in progress';
const originalRender=render;
const jsonEditor=(id, value)=>`<textarea id="${id}" rows="18" spellcheck="false">${pretty(value)}</textarea>`;
const exampleWorkflow=()=>({title:'Connected mission',steps:[{capability:caps.find(c=>c.mode!=='disabled')?.name||'project.capability',input:{}}],budget_microunits:1000000,max_tool_calls:20,deadline_seconds:3600});
render=async function(){
  await originalRender();
  const content=$('#content');
  const titles={workflow:'Workflow builder',templates:'Workflow templates',discovery:'Service status',groups:'Agent teams',semantic:'Semantic memory',operations:'Operations'};
  if(!titles[page]) {
    const heading=$('.banner h2');if(heading)heading.textContent='Your ecosystem. One shared mission.';
    return;
  }
  $('#page-title').textContent=titles[page];
  if(page==='workflow'){
    content.innerHTML=`<section class="panel"><h3>Build and validate a workflow</h3><p>Use exact capability inputs. Bindings reference earlier steps using a zero-based step number and a JSON pointer.</p>${jsonEditor('workflow-json',exampleWorkflow())}<details><summary>Binding and condition example</summary><pre>${pretty({capability:'redpa.chat',input:{conversation_id:'REPLACE_WITH_REAL_UUID'},bindings:{content:{step:0,pointer:'/result',format:'json'}},when:{step:0,pointer:'/result/failure_risk',op:'gte',value:0.7}})}</pre><p>This is a shape example, not a ready-to-run mission. Check your upstream output and input contracts.</p></details><div class="actions"><button data-v2="validate" class="secondary">Validate</button><button data-v2="queue" class="primary">Queue mission</button></div><label>Template name<input id="template-name" maxlength="100"></label><button data-v2="save-template" class="secondary">Save versioned template</button><div id="v2-result"></div></section>`;
  }else if(page==='templates'){
    const items=await api2('/templates');content.innerHTML=`<section class="panel">${items.length?items.map(t=>`<article class="memory-result"><h3>${escapeHTML(t.name)} · v${t.version}</h3><details><summary>Workflow</summary><pre>${pretty(t.workflow)}</pre></details><button data-template-run="${t.id}" class="primary">Queue with current permissions</button></article>`).join(''):empty('No saved templates','Save a validated workflow in Workflow builder.')}</section>`;
  }else if(page==='discovery'){
    const items=await api2('/discovery');content.innerHTML=`<section class="panel"><p>A health check is separate from a capability execution. “Unconfigured” means no health endpoint is configured.</p>${items.map(c=>`<article class="memory-result"><h3>${escapeHTML(c.name)} · ${escapeHTML(c.version)}</h3>${badge(c.status)} <span>Credential ${c.credential_ready?'available':'missing'}</span>${c.http_status?` · HTTP ${c.http_status}`:''}</article>`).join('')}</section>${me.role==='admin'?`<section class="panel"><h3>Register a capability</h3><p>Origin must already be in the operator allowlist. Registration grants no execution permission. Use a new version for contract changes.</p>${jsonEditor('capability-json',{name:'rednew.read',project:'rednew',version:'1.0.0',description:'Describe this capability',mode:'http',protocol:'nexus',workspace_binding:me.workspace,effect:'read',approval:false,endpoint:'http://127.0.0.1:8120/execute',health_endpoint:'http://127.0.0.1:8120/health',credential_env:'NEXUS_REDNEW_TOKEN',input_schema:{type:'object'},output_schema:{type:'object'}})}<button data-v2="register" class="primary">Register contract</button><div id="v2-result"></div></section>`:''}`;
  }else if(page==='operations'){
    if(me.role!=='admin'){content.innerHTML=empty('Administrator access required','Operations contains workspace-level metrics.');return;}
    const [ops,dead]=await Promise.all([api2('/operations'),api2('/dead-letters')]);
    content.innerHTML=`<div class="stats"><article class="stat"><span>Workers alive</span><strong>${ops.workers_alive}</strong><small>${ops.workers_stale} stale registrations</small></article><article class="stat"><span>Reserved cost</span><strong>${ops.reserved_cost_microunits}</strong><small>Micro-units; not a provider invoice</small></article><article class="stat"><span>Pending events</span><strong>${ops.outbox_pending}</strong><small>Broker ${ops.broker_enabled?'enabled':'disabled; local audit retained'}</small></article></div><section class="panel"><h3>Run counts</h3><pre>${pretty(ops.runs)}</pre><h3>Failed and uncertain missions</h3><p>Uncertain effects must be reconciled. Read-only failed workflows can be queued as a new run through the API.</p>${runTable(dead)}</section>`;
  }else if(page==='semantic'){
    content.innerHTML=`<section class="panel"><h3>Search by meaning</h3><p>Requires the operator-configured embedding provider. Indexing sends only this namespace’s authorized memory text to that provider. Up to 500 current records per namespace.</p><label>Namespace<input id="semantic-namespace" value="shared"></label><label>Question<input id="semantic-query"></label><div class="actions"><button data-v2="index-memory" class="secondary">Index current records</button><button data-v2="search-memory" class="primary">Search</button></div><div id="v2-result"></div></section>`;
  }else if(page==='groups'){
    const agents=await api('/agents');content.innerHTML=`<section class="panel"><h3>Delegate independent workflows</h3><p>Each assignment runs within its agent’s capability scope. Assigned budgets must fit the group budget. Use worker concurrency greater than one for parallel execution.</p><details><summary>Your agent IDs</summary><pre>${pretty(agents.map(a=>({id:a.id,name:a.name,capabilities:a.capabilities})))}</pre></details>${jsonEditor('group-json',{title:'Coordinated mission',budget_microunits:1000000,assignments:[{agent_id:agents[0]?.id||'CREATE_AN_AGENT_FIRST',workflow:exampleWorkflow()}]})}<button data-v2="group" class="primary">Queue group</button><div id="v2-result"></div></section>`;
  }
};
let v2RequestKey=crypto.randomUUID();
$('#content').addEventListener('input',()=>{v2RequestKey=crypto.randomUUID();});
$('#content').addEventListener('click',async event=>{
  const button=event.target.closest('[data-v2], [data-template-run]');if(!button)return;
  button.disabled=true;
  try{
    const action=button.dataset.v2;let result;
    const post=(path,data)=>api2(path,{method:'POST',headers:{'Idempotency-Key':v2RequestKey},body:data===undefined?undefined:JSON.stringify(data)});
    if(action==='validate')result=await post('/validate',JSON.parse($('#workflow-json').value));
    if(action==='queue'){result=await api('/runs',{method:'POST',headers:{'Idempotency-Key':v2RequestKey},body:$('#workflow-json').value});await inspectRun(result.id);return;}
    if(action==='save-template')result=await post('/templates',{name:$('#template-name').value,workflow:JSON.parse($('#workflow-json').value)});
    if(action==='register')result=await post('/capabilities',JSON.parse($('#capability-json').value));
    if(action==='group')result=await post('/mission-groups',JSON.parse($('#group-json').value));
    if(action==='index-memory')result=await post('/memory/index/'+encodeURIComponent($('#semantic-namespace').value));
    if(action==='search-memory')result=await post('/memory/search',{namespace:$('#semantic-namespace').value,query:$('#semantic-query').value});
    if(button.dataset.templateRun){result=await post('/templates/'+button.dataset.templateRun+'/runs');await inspectRun(result.id);return;}
    if(result && $('#v2-result'))$('#v2-result').innerHTML=`<pre>${pretty(result)}</pre>`;
  }catch(error){notice(error.message);}finally{button.disabled=false;}
});
