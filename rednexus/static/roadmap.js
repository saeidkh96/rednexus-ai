'use strict';
// Recipes are drafts: authorization and frozen-input review still happen server-side.
$('.release').textContent='PLATFORM PREVIEW · 2.0.0 RC2';
$('.sidebar-footer small').textContent='v2.0.0 RC2 · Acceptance gates pending';
let retainedWorkflow = null;
const r2Signout = signout;
signout = function(){retainedWorkflow=null;v2RequestKey=crypto.randomUUID();r2Signout();};
const r2Render = render;
render = async function() {
  await r2Render();
  if (page === 'workflow') {
    $('#content').insertAdjacentHTML('afterbegin', `<section class="panel"><h3>Start from a recipe or import a workflow</h3>
      <p>These recipes use sample observations with live project APIs. Creating a draft does not run it.</p>
      <label>Recipe<select id="recipe"><option value="maintenance-high">High risk → reviewed world advance</option>
      <option value="maintenance-low">Low risk → conditional skip check</option>
      <option value="maintenance-explanation">RedPulse result → reviewed RedPA chat</option></select></label>
      <div class="form-row"><label>Machine ID<input id="recipe-machine" value="motor-07" maxlength="200"></label>
      <label>Risk threshold<input id="recipe-threshold" type="number" min="0" max="1" step="0.05" value="0.5"></label></div>
      <label>Existing RedPA conversation UUID (chat recipe only)<input id="recipe-conversation" placeholder="Use a dedicated conversation"></label>
      <button class="primary" data-r2="draft">Create draft</button>
      <label>Import workflow JSON file<input id="workflow-file" type="file" accept=".json,application/json"></label>
      <div id="recipe-notes" role="status"></div></section>`);
    if (retainedWorkflow !== null) $('#workflow-json').value = retainedWorkflow;
    $('#workflow-json').addEventListener('input', () => { retainedWorkflow = $('#workflow-json').value; });
  }
  if (page === 'team' && me.role === 'admin') {
    const users = await api('/users');
    $('#content').insertAdjacentHTML('beforeend', `<section class="panel"><h3>Edit existing access</h3>
      <p>Choose an existing identity instead of creating another account. Enter exact grants, one per line.
      Your own access must be changed by another administrator.</p>
      <label>Identity<select id="access-user">${users.filter(u=>u.id!==me.id).map(u=>`<option value="${escapeHTML(u.id)}">${escapeHTML(u.username)}</option>`).join('')}</select></label>
      <label>Role<select id="access-role">${['reviewer','operator','viewer','admin'].map(r=>`<option>${r}</option>`).join('')}</select></label>
      <label>Exact grants<textarea id="access-grants" rows="6"></textarea></label>
      <label><input id="access-enabled" type="checkbox"> Membership enabled</label>
      <button class="primary" data-r2="access">Save access</button></section>`);
    const fill = () => {const u=users.find(x=>x.id===$('#access-user').value); if(!u)return;
      $('#access-role').value=u.role; $('#access-grants').value=u.grants.join('\n'); $('#access-enabled').checked=u.enabled;};
    $('#access-user').addEventListener('change', fill); fill();
  }
  if(page === 'groups') {
    const agents = await api('/agents');
    $('#content').insertAdjacentHTML('afterbegin', `<section class="panel"><h3>Propose a team workflow</h3>
      <p>Choose up to five profiles and enter an objective for each. Model profiles require a configured provider.
      Review the generated assignments before Queue group.</p><label>Team title<input id="team-title" value="Coordinated investigation"></label>
      <label>Total budget (micro-units)<input id="team-budget" type="number" value="10000000" min="0" max="1000000000"></label>
      ${agents.map(a=>`<label><input type="checkbox" class="team-agent" value="${escapeHTML(a.id)}"> ${escapeHTML(a.name)}</label>
      <label>Objective for ${escapeHTML(a.name)}<input data-team-objective="${escapeHTML(a.id)}" maxlength="3000"></label>`).join('')}
      <button data-r2="team-plan" class="secondary">Propose assignments</button><div id="team-plan-notes"></div></section>`);
    const groups = await api2('/mission-groups');
    $('#content').insertAdjacentHTML('beforeend', `<section class="panel"><h3>Submitted teams</h3>${groups.map(g=>`<p>${escapeHTML(g.title)} <button data-group-status="${escapeHTML(g.id)}">Check progress</button></p>`).join('') || '<p>No submitted teams yet.</p>'}<div id="group-status"></div></section>`);
  }
};
const r2Inspect = inspectRun;
inspectRun = async function(id) {
  await r2Inspect(id);
  $('#run-extra').insertAdjacentHTML('beforebegin', `<button class="secondary" data-evidence="${escapeHTML(id)}">Download execution evidence</button>`);
};
// The primary entry now opens the complete builder, avoiding the per-tool JSON modal.
$('#new-mission').addEventListener('click', async event => {
  event.stopImmediatePropagation();
  if(!['admin','operator'].includes(me.role)){notice('An operator or administrator role is required.');return;}
  v2RequestKey=crypto.randomUUID();
  page='workflow'; try {await render();} catch(error){notice(error.message);}
}, true);
$('#content').addEventListener('change', async event => {
  if(event.target.id!=='workflow-file')return;
  try {
    const file=event.target.files[0]; if(!file)return;
    if(file.size>65536)throw new Error('Workflow file must be at most 64 KiB.');
    const text=await file.text(), value=JSON.parse(text);
    if(!value || !Array.isArray(value.steps))throw new Error('Import a complete workflow with a steps array.');
    retainedWorkflow=JSON.stringify(value,null,2); $('#workflow-json').value=retainedWorkflow;
    v2RequestKey=crypto.randomUUID(); notice('Imported draft. Validate before queuing.');
  }catch(error){notice(error.message);}
});
function downloadEvidence(value,id){
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=`nexus-evidence-${id}.json`;a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('#content').addEventListener('click', async event => {
  const b=event.target.closest('[data-r2], [data-evidence], [data-group-status]');if(!b)return;
  b.disabled=true;
  try {
    if(b.dataset.r2==='draft'){
      const data={recipe:$('#recipe').value,machine_id:$('#recipe-machine').value,
        threshold:Number($('#recipe-threshold').value)};
      if(data.recipe==='maintenance-explanation')data.conversation_id=$('#recipe-conversation').value || null;
      const result=await api2('/workflow-drafts',{method:'POST',body:JSON.stringify(data)});
      retainedWorkflow=JSON.stringify(result.workflow,null,2);$('#workflow-json').value=retainedWorkflow;
      v2RequestKey=crypto.randomUUID();
      $('#recipe-notes').innerHTML=`<p>${result.notes.map(escapeHTML).join('<br>')}</p>
        <p>Missing execution grants: ${escapeHTML(result.missing_grants.join(', ')||'none')}</p>
        <p>Unavailable capabilities: ${escapeHTML(result.unavailable_capabilities.join(', ')||'none')}</p>
        <p>Separate reviewer needs: ${escapeHTML(result.review_grants.join(', ')||'none')}</p>`;
    }
    if(b.dataset.r2==='team-plan'){
      const selected=[...document.querySelectorAll('.team-agent:checked')];
      if(!selected.length||selected.length>5)throw new Error('Choose between one and five agents.');
      const objectives=selected.map(a=>({agent_id:a.value,objective:document.querySelector(`[data-team-objective="${a.value}"]`).value}));
      const result=await api2('/agent-teams/plan',{method:'POST',body:JSON.stringify({title:$('#team-title').value,
        budget_microunits:Number($('#team-budget').value),objectives})});
      $('#group-json').value=JSON.stringify(result.group,null,2);v2RequestKey=crypto.randomUUID();
      $('#team-plan-notes').textContent='Proposal ready. Nothing has been queued. Review assignments below.';
    }
    if(b.dataset.r2==='access'){
      const id=$('#access-user').value;if(!id)throw new Error('Choose an identity.');
      await api('/users/'+encodeURIComponent(id)+'/access',{method:'PUT',body:JSON.stringify({
        role:$('#access-role').value,grants:$('#access-grants').value.split('\n').map(s=>s.trim()).filter(Boolean),
        enabled:$('#access-enabled').checked})});
      notice('Access updated. Execution rechecks permissions.');
    }
    if(b.dataset.evidence)downloadEvidence(await api2('/runs/'+b.dataset.evidence+'/evidence'),b.dataset.evidence);
    if(b.dataset.groupStatus){const data=await api2('/mission-groups/'+b.dataset.groupStatus);
      $('#group-status').innerHTML=`<pre>${pretty(data)}</pre>`;}
  }catch(error){notice(error.message);}finally{b.disabled=false;}
});
