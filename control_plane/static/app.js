const $ = (id) => document.getElementById(id);

function escHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(s) {
  return String(s ?? '').replace(/'/g, "\\'");
}

function relTime(iso) {
  if (!iso) return '—';
  const delta = (Date.now() - new Date(iso).getTime()) / 1000;
  if (delta < 2)    return 'just now';
  if (delta < 60)   return `${Math.floor(delta)}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  return new Date(iso).toLocaleTimeString();
}

function clockStamp(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString('en-GB', {
    hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function truncId(id) {
  if (!id) return '—';
  return id.length > 13 ? `${id.slice(0, 8)}…` : id;
}

const BADGE_MAP = {
  succeeded:        'green',
  ready:            'green',
  COMPLETE:         'green',
  PENDING:          'amber',
  ENQUEUED:         'sky',
  sent:             'sky',
  connecting:       'amber',
  RETRIES_EXCEEDED: 'red',
  ERROR:            'red',
  failed:           'red',
  timed_out:        'amber',
  CANCELLED:        'slate',
  queued:           'slate',
  closed:           'slate',
};

function badge(status) {
  const cls = BADGE_MAP[status] ?? 'slate';
  return `<span class="badge badge-${cls}">${escHtml(status ?? '—')}</span>`;
}

function dirIcon(dir) {
  if (dir === 'inbound')  return `<span class="ev-dir ev-dir-in"  title="inbound">←</span>`;
  if (dir === 'outbound') return `<span class="ev-dir ev-dir-out" title="outbound">→</span>`;
  return `<span class="ev-dir ev-dir-sys" title="system">·</span>`;
}

function renderConnection(state) {
  const el    = $('connection-status');
  const label = $('conn-label');
  const s     = state.session;

  el.className = 'conn-pill';

  if (!s) {
    el.classList.add('conn-none');
    label.textContent = 'No connection';
  } else if (s.status === 'ready') {
    el.classList.add('conn-ready');
    label.textContent = `${s.app_name}  ready`;
  } else if (s.status === 'connecting') {
    el.classList.add('conn-connecting');
    label.textContent = `${s.app_name}  connecting`;
  } else {
    el.classList.add('conn-closed');
    label.textContent = `${s.app_name}  ${s.status}`;
  }
}

function renderSession(state) {
  const strip  = $('session-strip');
  const notice = $('no-conn-notice');
  const s      = state.session;

  if (!s) {
    strip.hidden  = true;
    notice.hidden = false;
    return;
  }

  notice.hidden = true;
  strip.hidden  = false;

  const info = s.executor_info ?? {};

  $('sess-app').textContent          = s.app_name || '—';
  $('sess-executor-id').textContent  = info.executor_id || '—';
  $('sess-app-version').textContent  = info.application_version || '—';

  const sesEl = $('sess-session-id');
  sesEl.textContent  = truncId(s.session_id);
  sesEl.title        = s.session_id || '';

  $('sess-connected-at').textContent = relTime(s.connected_at);
  $('sess-last-seen').textContent    = relTime(s.last_seen_at);
}

function renderEvents(events) {
  const el = $('event-log');
  $('event-count').textContent = events.length;

  if (!events.length) {
    el.innerHTML = '<div class="empty-hint">No events yet</div>';
    return;
  }

  el.innerHTML = events.map(ev => `
    <div class="event-row">
      <span class="ev-time">${clockStamp(ev.timestamp)}</span>
      ${dirIcon(ev.direction)}
      <span class="ev-type">${escHtml(ev.message_type)}</span>
      <span class="ev-summary">${escHtml(ev.summary)}</span>
    </div>
  `).join('');
}

function renderRequests(requests) {
  const el = $('request-log');
  $('request-count').textContent = requests.length;

  if (!requests.length) {
    el.innerHTML = '<div class="empty-hint">No requests yet</div>';
    return;
  }

  el.innerHTML = requests.map(req => `
    <div class="req-row">
      <div>
        <div class="req-type">${escHtml(req.message_type)}</div>
        <div class="req-id">${escHtml(req.request_id)}</div>
      </div>
      ${badge(req.status)}
      <div class="req-time">${relTime(req.created_at)}</div>
    </div>
  `).join('');
}

function renderWorkflows(workflows) {
  const el = $('workflow-list');
  $('workflow-count').textContent = workflows.length;

  if (!workflows.length) {
    el.innerHTML = '<div class="empty-hint">No workflow data — use "List Workflows" to fetch.</div>';
    return;
  }

  const rows = workflows.map(wf => {
    const id     = wf.WorkflowUUID || '';
    const name   = wf.WorkflowName || wf.WorkflowClassName || '—';
    const status = wf.Status || '—';
    const queue  = wf.QueueName || '—';
    const createdAt = wf.CreatedAt;
    const updatedAt = wf.UpdatedAt;

    return `<tr>
      <td class="td-id" title="${escHtml(id)}">${escHtml(truncId(id))}</td>
      <td class="td-mono">${escHtml(name)}</td>
      <td>${badge(status)}</td>
      <td class="td-dim">${escHtml(queue)}</td>
      <td class="td-dim">${relTime(createdAt)}</td>
      <td class="td-dim">${relTime(updatedAt)}</td>
      <td>
        <div class="wf-actions">
          <button class="btn-sm" onclick="doInspect('${escAttr(id)}')">inspect</button>
          <button class="btn-sm" onclick="doResume('${escAttr(id)}')">resume</button>
          <button class="btn-sm btn-sm-fork" onclick="doFork('${escAttr(id)}')">fork</button>
          <button class="btn-sm btn-sm-red" onclick="doCancel('${escAttr(id)}')">cancel</button>
        </div>
      </td>
    </tr>`;
  }).join('');

  el.innerHTML = `
    <table class="workflow-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Name / Class</th>
          <th>Status</th>
          <th>Queue</th>
          <th>Created</th>
          <th>Updated</th>
          <th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function callApi(path, body, label) {
  const msg = $('action-msg');
  msg.hidden    = false;
  msg.className = 'action-msg';
  msg.textContent = `${label}…`;

  try {
    const res  = await fetch(path, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    body != null ? JSON.stringify(body) : undefined,
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || res.statusText);

    msg.className   = 'action-msg ok';
    msg.textContent = `${label} → ${json.status || 'sent'}`;
    await refresh();
    setTimeout(() => { msg.hidden = true; }, 3000);
    return json;
  } catch (err) {
    msg.className   = 'action-msg err';
    msg.textContent = `${label} failed: ${err.message}`;
    setTimeout(() => { msg.hidden = true; }, 5000);
    throw err;
  }
}

function showInspect(title, content) {
  $('inspect-title').textContent  = title;
  $('inspect-body').textContent   = content;
  $('inspect-overlay').style.display = 'flex';
}

function closeInspect() {
  $('inspect-overlay').style.display = 'none';
}

window.doInspect = async (id) => {
  try {
    const res = await callApi(
      '/api/control-plane/get-workflow',
      { workflow_id: id, load_input: true, load_output: true },
      'get_workflow',
    );
    if (res.response) {
      showInspect(`workflow: ${id}`, JSON.stringify(res.response, null, 2));
    }
  } catch (_) {}
};

window.doCancel = async (id) => {
  if (!confirm(`Cancel workflow ${id}?`)) return;
  try {
    await callApi('/api/control-plane/cancel', { workflow_id: id }, 'cancel');
  } catch (_) {}
};

window.doResume = async (id) => {
  try {
    await callApi('/api/control-plane/resume', { workflow_id: id }, 'resume');
  } catch (_) {}
};

const ACTIVE_FORK_SOURCE_STATUSES = new Set(['PENDING', 'ENQUEUED', 'DELAYED']);

let forkState = {
  workflowId: null,
  steps: [],
  selectedStep: null,
  workflowInputText: '',
  sourceStatus: null,
  sourceIsActive: false,
  stagedWorkflowId: null,
};

function resetForkPostStage() {
  forkState.stagedWorkflowId = null;
  $('fork-post-stage').hidden = true;
  $('fork-post-stage-body').textContent = 'Stage an edited-input fork to review it before execution.';
  $('fork-execute-btn').disabled = true;
}

function showForkPostStage(response) {
  const stagedWorkflowId = response?.new_workflow_id;
  forkState.stagedWorkflowId = stagedWorkflowId || null;
  $('fork-post-stage').hidden = false;
  $('fork-post-stage-body').textContent = stagedWorkflowId
    ? `Fork ${stagedWorkflowId} is staged as PENDING. Review it now, or execute it when ready.`
    : 'Fork staged as PENDING. Review it now, or execute it when ready.';
  $('fork-execute-btn').disabled = !stagedWorkflowId;
}

function renderForkSourceControls() {
  const sourceStatus = forkState.sourceStatus || '—';
  const isActive = forkState.sourceIsActive;
  $('fork-source-status').innerHTML = badge(sourceStatus);
  $('fork-cancel-original-row').hidden = !isActive;
  $('fork-cancel-original').checked = isActive;
}

function forkStepDurationMs(step) {
  const s = parseInt(step.started_at_epoch_ms, 10);
  const e = parseInt(step.completed_at_epoch_ms, 10);
  if (!isNaN(s) && !isNaN(e) && e >= s) return e - s;
  return null;
}

function forkStepTimestamp(step) {
  const ms = parseInt(step.completed_at_epoch_ms, 10);
  if (isNaN(ms)) return null;
  return new Date(ms).toLocaleTimeString('en-GB', { hour12: false });
}

function forkStepBadge(step) {
  if (step.error)              return badge('ERROR');
  if (step.completed_at_epoch_ms) return badge('COMPLETE');
  return badge('PENDING');
}

function renderForkSteps() {
  const { steps, selectedStep } = forkState;
  const list = $('fork-step-list');
  const empty = $('fork-steps-empty');
  const overrideRaw = $('fork-input-override').value.trim();
  const hasOverride = overrideRaw.length > 0;

  if (!steps.length) {
    $('fork-steps-hint-text').textContent = 'No steps recorded for this workflow.';
    empty.style.display = 'flex';
    list.style.display  = 'none';
    $('fork-submit-btn').disabled = true;
    return;
  }

  empty.style.display = 'none';
  list.style.display  = 'block';

  list.innerHTML = steps.map((step, idx) => {
    const fid      = step.function_id ?? idx;
    const isFork   = fid === selectedStep;
    const isPreserved = selectedStep !== null && fid < selectedStep;
    const isPending   = selectedStep !== null && fid > selectedStep;

    let stateClass = '';
    if (isFork)       stateClass = 'is-fork-point';
    else if (isPreserved) stateClass = 'is-preserved';
    else if (isPending)   stateClass = 'is-pending';

    const ts        = forkStepTimestamp(step);
    const dur       = forkStepDurationMs(step);
    const durText   = dur !== null ? `${dur}ms` : '';
    const tsText    = ts ? ts : '';
    const metaText  = [tsText, durText].filter(Boolean).join(' · ');
    const restartNote = fid === 0 ? ' <span class="fork-step-note" style="color:var(--text-3)">≡ restart</span>' : '';

    const indicatorText = isFork
      ? (hasOverride && fid === 0 ? '✎ rerun with edited input' : '↻ re-execute')
      : (isPreserved ? '✓ preserved' : '');

    return `<div class="fork-step ${stateClass}" onclick="forkSelectStep(${fid})">
      <div class="fork-step-num">
        <div class="fork-step-node">${fid}</div>
      </div>
      <div class="fork-step-body">
        <div class="fork-step-name">${escHtml(step.function_name || '—')}</div>
        <div class="fork-step-meta">
          ${forkStepBadge(step)}
          ${metaText ? `<span class="fork-step-time">${escHtml(metaText)}</span>` : ''}
          ${restartNote}
        </div>
      </div>
      <div class="fork-step-indicator">${escHtml(indicatorText)}</div>
    </div>`;
  }).join('');

  const submitBtn   = $('fork-submit-btn');
  const submitLabel = $('fork-submit-label');

  if (selectedStep !== null) {
    const isRestart = selectedStep === 0;
    if (hasOverride) {
      submitLabel.textContent = 'Stage edited-input fork';
      submitBtn.disabled = !isRestart;
      $('fork-override-help').textContent = isRestart
        ? 'Edited input stages a new PENDING workflow from step 0 with the JSON override below.'
        : 'Edited input only supports a staged full rerun from step 0. Select step 0 to continue.';
    } else {
      submitLabel.textContent = isRestart
        ? 'Restart (fork from step 0)'
        : `Fork from step ${selectedStep}`;
      submitBtn.disabled = false;
      $('fork-override-help').textContent = 'Edited input is a shim-owned staged fork path. Add an override below to stage a new workflow from step 0 with new input; execution happens as a separate reviewed action.';
    }
  } else {
    submitLabel.textContent = 'Fork';
    submitBtn.disabled = true;
    $('fork-override-help').textContent = 'Edited input is a shim-owned staged fork path. Add an override below to stage a new workflow from step 0 with new input; execution happens as a separate reviewed action.';
  }
}

window.forkSelectStep = (functionId) => {
  forkState.selectedStep = functionId;
  renderForkSteps();
};

async function openForkModal(workflowId) {
  forkState = {
    workflowId,
    steps: [],
    selectedStep: null,
    workflowInputText: '',
    sourceStatus: null,
    sourceIsActive: false,
    stagedWorkflowId: null,
  };

  $('fork-wf-id-display').textContent = workflowId;
  $('fork-steps-hint-text').textContent = 'Loading steps…';
  $('fork-steps-empty').style.display = 'flex';
  $('fork-step-list').style.display   = 'none';
  $('fork-submit-btn').disabled = true;
  $('fork-submit-label').textContent  = 'Fork';
  $('fork-new-id').value = '';
  $('fork-input-override').value = '';
  $('fork-override-help').textContent = 'Edited input is a shim-owned staged fork path. Add an override below to stage a new workflow from step 0 with new input; execution happens as a separate reviewed action.';
  $('fork-source-status').textContent = '—';
  $('fork-cancel-original-row').hidden = true;
  resetForkPostStage();

  $('fork-overlay').style.display = 'flex';

  try {
    const workflowRes = await fetch('/api/control-plane/get-workflow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow_id: workflowId, load_input: true, load_output: false }),
    });
    const workflowJson = await workflowRes.json();
    if (workflowRes.ok) {
      const workflowOutput = workflowJson.response?.output ?? {};
      const sourceStatus = workflowOutput.Status || null;
      forkState.sourceStatus = sourceStatus;
      forkState.sourceIsActive = ACTIVE_FORK_SOURCE_STATUSES.has(sourceStatus);
      renderForkSourceControls();
      const inputSeed = workflowJson.input_override_seed;
      if (inputSeed && typeof inputSeed === 'object' && !Array.isArray(inputSeed)) {
        const seededJson = JSON.stringify(inputSeed, null, 2);
        forkState.workflowInputText = seededJson;
        $('fork-input-override').value = seededJson;
      }
    }
  } catch (_) {}

  try {
    const res = await fetch('/api/control-plane/list-steps', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ workflow_id: workflowId, load_output: false }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || res.statusText);

    const raw   = json.response?.output ?? [];
    forkState.steps = raw.slice().sort((a, b) => (a.function_id ?? 0) - (b.function_id ?? 0));

    if (forkState.steps.length > 0) {
      forkState.selectedStep = forkState.steps[0].function_id ?? 0;
    }

    renderForkSteps();
  } catch (err) {
    $('fork-steps-hint-text').textContent = `Failed to load steps: ${err.message}`;
    $('fork-steps-empty').style.display   = 'flex';
    $('fork-step-list').style.display     = 'none';
  }
}

function closeForkModal() {
  $('fork-overlay').style.display = 'none';
  resetForkPostStage();
}

window.doFork = (id) => openForkModal(id);

$('fork-cancel-btn').addEventListener('click', closeForkModal);
$('fork-backdrop').addEventListener('click', closeForkModal);
$('fork-close').addEventListener('click', closeForkModal);
$('fork-input-override').addEventListener('input', renderForkSteps);
$('fork-post-stage-dismiss').addEventListener('click', resetForkPostStage);

$('fork-execute-btn').addEventListener('click', async () => {
  const workflowId = forkState.stagedWorkflowId;
  if (!workflowId) return;
  try {
    await callApi('/api/control-plane/execute-staged-fork', { workflow_id: workflowId }, 'execute_staged_fork');
    resetForkPostStage();
  } catch (_) {}
});

$('fork-submit-btn').addEventListener('click', async () => {
  const { workflowId, selectedStep } = forkState;
  if (workflowId === null || selectedStep === null) return;

  const newId = $('fork-new-id').value.trim() || null;
  const overrideText = $('fork-input-override').value.trim();
  const body  = { workflow_id: workflowId, start_step: selectedStep };
  if (newId) body.new_workflow_id = newId;

  if (overrideText) {
    let parsedOverride;
    try {
      parsedOverride = JSON.parse(overrideText);
    } catch (_) {
      const msg = $('action-msg');
      msg.hidden = false;
      msg.className = 'action-msg err';
      msg.textContent = 'fork_workflow failed: Input override must be valid JSON';
      setTimeout(() => { msg.hidden = true; }, 5000);
      return;
    }
    body.input_override = parsedOverride;
    body.cancel_original_if_active = forkState.sourceIsActive && $('fork-cancel-original').checked;
  }

  try {
    const response = await callApi('/api/control-plane/fork', body, 'fork_workflow');
    if (body.input_override) {
      showForkPostStage(response.response);
      return;
    }
    closeForkModal();
  } catch (_) {}
});

$('btn-list-workflows').addEventListener('click', () =>
  callApi('/api/control-plane/list-workflows', {}, 'list_workflows'),
);

$('btn-list-queued').addEventListener('click', () =>
  callApi('/api/control-plane/list-queued-workflows', {}, 'list_queued_workflows'),
);

$('btn-recovery').addEventListener('click', () => {
  if (confirm('Trigger recovery? The executor will be asked to resume pending workflows.')) {
    callApi('/api/control-plane/recovery', {}, 'recovery');
  }
});

$('inspect-backdrop').addEventListener('click', closeInspect);
$('inspect-close').addEventListener('click', closeInspect);

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeInspect();
    closeForkModal();
  }
});

let pollFailed = false;

async function refresh() {
  try {
    const res   = await fetch('/api/control-plane/state');
    if (!res.ok) throw new Error(res.statusText);
    const state = await res.json();

    pollFailed = false;

    renderConnection(state);
    renderSession(state);
    renderEvents(state.events ?? []);
    renderRequests(state.requests ?? []);
    renderWorkflows(state.last_list_workflows_output ?? []);

    const ready = state.session?.status === 'ready';
    ['btn-list-workflows', 'btn-list-queued', 'btn-recovery'].forEach(id => {
      $(id).disabled = !ready;
    });

    $('poll-clock').textContent = new Date().toLocaleTimeString('en-GB', { hour12: false });
  } catch (err) {
    if (!pollFailed) {
      pollFailed = true;
      console.error('State poll failed:', err);
    }
  }
}

refresh();
setInterval(refresh, 1500);
