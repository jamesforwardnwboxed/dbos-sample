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

// Parse an ISO 8601 string OR an epoch-ms value (number or numeric string,
// as DBOS returns CreatedAt/UpdatedAt as stringified epoch ms).
function toDate(value) {
  if (value === null || value === undefined || value === '') return null;
  if (value instanceof Date) return value;
  if (typeof value === 'number') return new Date(value);
  if (typeof value === 'string' && /^-?\d+$/.test(value.trim())) {
    return new Date(Number(value));
  }
  const d = new Date(value);
  return isNaN(d.getTime()) ? null : d;
}

function relTime(iso) {
  const d = toDate(iso);
  if (!d) return '—';
  const delta = (Date.now() - d.getTime()) / 1000;
  if (delta < 2)    return 'just now';
  if (delta < 60)   return `${Math.floor(delta)}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  return d.toLocaleTimeString();
}

function clockStamp(iso) {
  const d = toDate(iso);
  if (!d) return '—';
  return d.toLocaleTimeString('en-GB', {
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
  SUCCESS:          'green',
  PENDING:          'amber',
  ENQUEUED:         'sky',
  DELAYED:          'sky',
  sent:             'sky',
  connecting:       'amber',
  RETRIES_EXCEEDED: 'red',
  MAX_RECOVERY_ATTEMPTS_EXCEEDED: 'red',
  ERROR:            'red',
  failed:           'red',
  timed_out:        'amber',
  CANCELLED:        'slate',
  cancelled:        'slate',
  queued:           'slate',
  closed:           'slate',
};

function badge(status) {
  const cls = BADGE_MAP[status] ?? 'slate';
  return `<span class="badge badge-${cls}">${escHtml(status ?? '—')}</span>`;
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

  const execEl = $('sess-executor-id');
  execEl.textContent = truncId(info.executor_id);
  execEl.title       = info.executor_id || '';

  const verEl = $('sess-app-version');
  verEl.textContent  = truncId(info.application_version);
  verEl.title        = info.application_version || '';

  const sesEl = $('sess-session-id');
  sesEl.textContent  = truncId(s.session_id);
  sesEl.title        = s.session_id || '';

  $('sess-connected-at').textContent = relTime(s.connected_at);
  $('sess-last-seen').textContent    = relTime(s.last_seen_at);
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
    el.innerHTML = '<div class="empty-hint">No workflow data yet. The list refreshes automatically every 5 seconds once an executor is ready.</div>';
    return;
  }

  const rows = workflows.map(wf => {
    const id     = wf.WorkflowUUID || '';
    const name   = wf.WorkflowName || wf.WorkflowClassName || '—';
    const status = wf.Status || '—';
    const queue  = wf.QueueName || '—';
    const createdAt = wf.CreatedAt;
    const updatedAt = wf.UpdatedAt;
    const primaryAction = status === 'SUCCESS'
      ? `<button class="btn-sm" onclick="doRestart('${escAttr(id)}')">restart</button>`
      : `<button class="btn-sm" onclick="doResume('${escAttr(id)}')">resume</button>`;

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
          ${primaryAction}
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

window.doRestart = async (id) => {
  try {
    await callApi('/api/control-plane/restart', { workflow_id: id }, 'restart');
  } catch (_) {}
};

const ACTIVE_FORK_SOURCE_STATUSES = new Set(['PENDING', 'ENQUEUED', 'DELAYED']);

let forkState = {
  workflowId: null,
  steps: [],
  boundaries: [],
  selectedStep: null,
  workflowInputText: '',
  workflowInputSeed: '',
  workflowInputSerialization: null,
  workflowInputMode: 'raw',
  stepOutputEdits: {},
  rawStepOutputs: {},
  sourceStatus: null,
  sourceIsActive: false,
  stagedWorkflowId: null,
};

function workflowInputEdited() {
  return $('fork-input-override').value.trim() !== (forkState.workflowInputSeed || '').trim();
}

function isPythonPickleSerialization(serialization) {
  return serialization === 'py_pickle';
}

function isGoDbosJsonSerialization(serialization) {
  return serialization === 'DBOS_JSON';
}

function isRawFriendlySerialization(serialization) {
  return serialization === 'java_jackson' || serialization === 'js_superjson' || serialization == null;
}

function decodeGoDbosJsonPayload(rawValue) {
  if (typeof rawValue !== 'string' || rawValue === '') return '';
  try {
    return JSON.stringify(JSON.parse(atob(rawValue)), null, 2);
  } catch (_) {
    return rawValue;
  }
}

function encodeGoDbosJsonPayload(editorValue) {
  const parsed = editorValue.trim() ? JSON.parse(editorValue) : null;
  return btoa(JSON.stringify(parsed));
}

function describeSerializationHelp(serialization, mode) {
  if (isPythonPickleSerialization(serialization)) {
    return mode === 'python-decoded'
      ? 'Python pickle payloads are decoded through the Python serializer for editing and re-serialized on submit.'
      : 'Python pickle payloads are shown raw when no decoded editor is available.';
  }
  if (isGoDbosJsonSerialization(serialization)) {
    return mode === 'decoded-json'
      ? 'Go DBOS_JSON payloads are shown decoded as JSON and re-encoded on submit.'
      : 'Edit the exact stored payload for this serializer.';
  }
  return 'Edit the exact stored payload for this serializer.';
}

function renderForkInputSerialization() {
  const label = forkState.workflowInputSerialization || 'unknown';
  $('fork-input-serialization').textContent = `serialization: ${label}`;
  $('fork-input-help').textContent = describeSerializationHelp(label, forkState.workflowInputMode);
  $('fork-input-override').disabled = isPythonPickleSerialization(label) && forkState.workflowInputMode !== 'python-decoded';
}

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

function hasStepOutput(step) {
  return step && Object.prototype.hasOwnProperty.call(step, 'output') && step.output !== null;
}

function isTerminalWorkflowStatus(status) {
  return ['SUCCESS', 'ERROR', 'CANCELLED', 'RETRIES_EXCEEDED', 'MAX_RECOVERY_ATTEMPTS_EXCEEDED'].includes(status);
}

function computeForkBoundaries() {
  const boundaries = [{
    function_id: 0,
    function_name: 'restart workflow',
    synthetic: true,
    boundary_type: 'restart',
  }];
  const stepIds = new Set([0]);

  for (const step of forkState.steps) {
    const fid = step.function_id ?? 0;
    if (!stepIds.has(fid)) {
      boundaries.push({ ...step, synthetic: false, boundary_type: 'recorded' });
      stepIds.add(fid);
    }
  }

  const lastStep = forkState.steps[forkState.steps.length - 1];
  if (lastStep && !isTerminalWorkflowStatus(forkState.sourceStatus || '')) {
    const nextFunctionId = (lastStep.function_id ?? 0) + 1;
    if (!stepIds.has(nextFunctionId)) {
      boundaries.push({
        function_id: nextFunctionId,
        function_name: `rerun after ${lastStep.function_name || `step ${lastStep.function_id}`}`,
        synthetic: true,
        boundary_type: 'next',
        prior_step_name: lastStep.function_name || null,
      });
    }
  }

  boundaries.sort((a, b) => (a.function_id ?? 0) - (b.function_id ?? 0));
  return boundaries;
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

function describeForkSelection(step) {
  if (!step) return 'Select where the fork should resume.';
  const fid = step.function_id ?? 0;
  if (fid === 0) {
    return 'Selected rerun point: restart the workflow from the beginning.';
  }
  if (step.boundary_type === 'next') {
    return `Selected rerun point: start at step ${fid}, after ${step.prior_step_name || `step ${fid - 1}`}.`;
  }
  return `Selected rerun point: re-run from step ${fid} (${step.function_name || 'unnamed step'}).`;
}

function renderForkSteps() {
  const { boundaries, selectedStep } = forkState;
  const list = $('fork-step-list');
  const empty = $('fork-steps-empty');
  const inputOverrideField = $('fork-input-override');
  const hasOverride = workflowInputEdited();
  const selectedBoundary = boundaries.find((step) => (step.function_id ?? null) === selectedStep) || null;

  $('fork-selection-summary').textContent = describeForkSelection(selectedBoundary);

  if (!boundaries.length) {
    $('fork-steps-hint-text').textContent = 'No fork boundaries available for this workflow.';
    empty.style.display = 'flex';
    list.style.display  = 'none';
    $('fork-submit-btn').disabled = true;
    $('fork-selection-summary').textContent = 'No fork boundaries available for this workflow.';
    renderForkStepOverrides();
    return;
  }

  empty.style.display = 'none';
  list.style.display  = 'block';

  list.innerHTML = boundaries.map((step, idx) => {
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
    const stepLabel = fid === 0 ? 'restart' : `step ${fid}`;
    const restartNote = fid === 0
      ? ' <span class="fork-step-note">full restart</span>'
      : (step.synthetic
        ? ' <span class="fork-step-note">resume after prior step</span>'
        : '');

    const indicatorText = isFork
      ? 'selected rerun point'
      : (isPreserved ? '✓ preserved' : '');

    return `<div class="fork-step ${stateClass}" onclick="forkSelectStep(${fid})">
      <div class="fork-step-num">
        <div class="fork-step-node">${escHtml(stepLabel)}</div>
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
  const runBtn      = $('fork-run-btn');
  const runLabel    = $('fork-run-label');

  if (selectedStep !== null) {
    inputOverrideField.disabled = false;
    submitBtn.disabled = false;
    runBtn.disabled = false;
    if (hasOverride) {
      submitLabel.textContent = 'Stage edited fork';
      runLabel.textContent = 'Run edited fork now';
    } else {
      submitLabel.textContent = selectedStep === 0
        ? 'Stage restart from step 0'
        : `Stage fork from step ${selectedStep}`;
      runLabel.textContent = selectedStep === 0
        ? 'Restart now'
        : `Fork & run from step ${selectedStep}`;
    }
    $('fork-override-help').textContent = 'Edited recovery stages a new PENDING fork for review. You can edit workflow input and preserved checkpoint outputs before executing the fork.';
  } else {
    inputOverrideField.disabled = true;
    submitLabel.textContent = 'Stage fork';
    runLabel.textContent = 'Run now';
    submitBtn.disabled = true;
    runBtn.disabled = true;
    $('fork-override-help').textContent = 'Edited recovery stages a new PENDING fork for review. You can edit workflow input and preserved checkpoint outputs before executing the fork.';
  }

  renderForkStepOverrides();
}

function renderForkStepOverrides() {
  const container = $('fork-step-overrides');
  const empty = $('fork-step-overrides-empty');
  const { steps, selectedStep, stepOutputEdits } = forkState;

  const editableSteps = steps.filter((step) => (step.function_id ?? -1) < (selectedStep ?? -1) && hasStepOutput(step));
  if (!editableSteps.length) {
    empty.textContent = selectedStep === 0
      ? 'No preserved step outputs exist before a full restart.'
      : 'No preserved step outputs are available before the selected fork boundary.';
    empty.hidden = false;
    container.querySelectorAll('.fork-step-edit-card').forEach((node) => node.remove());
    return;
  }

  empty.hidden = true;
  container.querySelectorAll('.fork-step-edit-card').forEach((node) => node.remove());
  const cards = editableSteps.map((step) => {
    const fid = String(step.function_id ?? '');
    const rawMetadata = forkState.rawStepOutputs[fid] || null;
    const serialization = rawMetadata?.serialization || 'unknown';
    const editor = rawMetadata?.editor || null;
    const isGoJson = isGoDbosJsonSerialization(serialization) || editor?.mode === 'decoded-json';
    const isPythonPickle = isPythonPickleSerialization(serialization);
    const currentText = Object.prototype.hasOwnProperty.call(stepOutputEdits, fid)
      ? stepOutputEdits[fid]
      : (editor?.mode === 'python-value'
        ? JSON.stringify(editor.value, null, 2)
        : (isGoJson ? decodeGoDbosJsonPayload(rawMetadata?.value) : (rawMetadata?.value ?? JSON.stringify(step.output, null, 2))));
    const hint = editor?.mode === 'python-value'
      ? `Decoded Python value editor · serialization ${serialization}`
      : (isPythonPickle
      ? `Python pickle payload shown raw · serialization ${serialization}`
      : (isGoJson
        ? `Decoded JSON editor for Go payload · serialization ${serialization}`
        : `Preserved raw output · serialization ${serialization}`));
    return `
      <div class="fork-step-edit-card">
        <div class="fork-step-edit-head">
          <span class="fork-step-edit-title mono">step ${escHtml(fid)} · ${escHtml(step.function_name || '—')}</span>
          <span class="fork-step-edit-hint">${escHtml(hint)}</span>
        </div>
        <textarea
          class="fork-input mono fork-step-edit-input"
          data-step-output-id="${escHtml(fid)}"
          rows="4"
          spellcheck="false"
          ${(isPythonPickle && editor?.mode !== 'python-value') ? 'disabled' : ''}
        >${escHtml(currentText)}</textarea>
      </div>
    `;
  }).join('');
  container.insertAdjacentHTML('beforeend', cards);
  container.querySelectorAll('[data-step-output-id]').forEach((node) => {
    node.addEventListener('input', (event) => {
      const target = event.target;
      forkState.stepOutputEdits[target.dataset.stepOutputId] = target.value;
    });
  });
}

window.forkSelectStep = (functionId) => {
  forkState.selectedStep = functionId;
  renderForkSteps();
};

async function openForkModal(workflowId) {
  forkState = {
    workflowId,
    steps: [],
    boundaries: [],
    selectedStep: null,
    workflowInputText: '',
    workflowInputSeed: '',
    workflowInputSerialization: null,
    workflowInputMode: 'raw',
    stepOutputEdits: {},
    rawStepOutputs: {},
    sourceStatus: null,
    sourceIsActive: false,
    stagedWorkflowId: null,
  };

  $('fork-wf-id-display').textContent = workflowId;
  $('fork-steps-hint-text').textContent = 'Loading steps…';
  $('fork-steps-empty').style.display = 'flex';
  $('fork-step-list').style.display   = 'none';
  $('fork-submit-btn').disabled = true;
  $('fork-submit-label').textContent  = 'Stage fork';
  $('fork-run-btn').disabled = true;
  $('fork-run-label').textContent  = 'Run now';
  $('fork-selection-summary').textContent = 'Select where the fork should resume.';
  $('fork-new-id').value = '';
  $('fork-input-override').value = '';
  $('fork-input-override').disabled = false;
  $('fork-input-serialization').textContent = 'serialization: unknown';
  $('fork-input-help').textContent = 'Edit the exact stored payload for this serializer.';
  $('fork-override-help').textContent = 'Edited recovery stages a new PENDING fork for review. You can edit workflow input and preserved checkpoint outputs before executing the fork.';
  $('fork-source-status').textContent = '—';
  $('fork-cancel-original-row').hidden = true;
  $('fork-step-overrides-empty').hidden = false;
  $('fork-step-overrides-empty').textContent = 'Select a fork boundary to edit preserved step outputs.';
  $('fork-step-overrides').querySelectorAll('.fork-step-edit-card').forEach((node) => node.remove());
  resetForkPostStage();

  document.body.classList.add('modal-open');
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
      const rawInput = workflowJson.raw_workflow_input;
      if (rawInput && typeof rawInput === 'object') {
        forkState.workflowInputSerialization = rawInput.serialization || null;
        if (rawInput.editor?.mode === 'python-args-kwargs') {
          const decoded = JSON.stringify(rawInput.editor.value, null, 2);
          forkState.workflowInputMode = 'python-decoded';
          forkState.workflowInputText = decoded;
          forkState.workflowInputSeed = decoded;
          $('fork-input-override').value = decoded;
        } else if (typeof rawInput.value === 'string') {
          if (isGoDbosJsonSerialization(forkState.workflowInputSerialization)) {
            const decoded = decodeGoDbosJsonPayload(rawInput.value);
            forkState.workflowInputMode = 'decoded-json';
            forkState.workflowInputText = decoded;
            forkState.workflowInputSeed = decoded;
            $('fork-input-override').value = decoded;
          } else {
            forkState.workflowInputMode = 'raw';
            forkState.workflowInputText = rawInput.value;
            forkState.workflowInputSeed = rawInput.value;
            $('fork-input-override').value = rawInput.value;
          }
        }
      }
      const inputSeed = workflowJson.workflow_input_seed;
      if (!forkState.workflowInputSeed && inputSeed && typeof inputSeed === 'object' && !Array.isArray(inputSeed)) {
        const seededJson = JSON.stringify(inputSeed, null, 2);
        forkState.workflowInputText = seededJson;
        forkState.workflowInputSeed = seededJson;
        $('fork-input-override').value = seededJson;
      } else if (!forkState.workflowInputSeed) {
        forkState.workflowInputSeed = '';
        $('fork-input-override').value = '';
      }
      renderForkInputSerialization();
    }
  } catch (_) {}

  try {
    const res = await fetch('/api/control-plane/list-steps', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
       body:    JSON.stringify({ workflow_id: workflowId, load_output: true }),
     });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || res.statusText);

     const raw   = json.response?.output ?? [];
      forkState.rawStepOutputs = json.raw_step_outputs || {};
      forkState.steps = raw.slice().sort((a, b) => (a.function_id ?? 0) - (b.function_id ?? 0));
      forkState.boundaries = computeForkBoundaries();

     if (forkState.boundaries.length > 0) {
       const preferredBoundary = forkState.boundaries.find((item) => item.boundary_type === 'next');
       forkState.selectedStep = preferredBoundary?.function_id ?? (forkState.boundaries[0].function_id ?? 0);
     }

    renderForkSteps();
  } catch (err) {
    $('fork-steps-hint-text').textContent = `Failed to load steps: ${err.message}`;
    $('fork-steps-empty').style.display   = 'flex';
    $('fork-step-list').style.display     = 'none';
  }
}

function closeForkModal() {
  document.body.classList.remove('modal-open');
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

async function submitForkWithMode(mode) {
  const { workflowId, selectedStep } = forkState;
  if (workflowId === null || selectedStep === null) return;

  const newId = $('fork-new-id').value.trim() || null;
  const body  = { workflow_id: workflowId, start_step: selectedStep, mode };
  if (newId) body.new_workflow_id = newId;

  if (workflowInputEdited()) {
    if (forkState.workflowInputMode === 'python-decoded') {
      try {
        body.workflow_input_override = JSON.parse($('fork-input-override').value);
      } catch (_) {
        const msg = $('action-msg');
        msg.hidden = false;
        msg.className = 'action-msg err';
        msg.textContent = 'fork_workflow failed: Python payload editor must be valid JSON';
        setTimeout(() => { msg.hidden = true; }, 5000);
        return;
      }
    } else if (isGoDbosJsonSerialization(forkState.workflowInputSerialization)) {
      try {
        body.raw_workflow_input_override = encodeGoDbosJsonPayload($('fork-input-override').value);
      } catch (_) {
        const msg = $('action-msg');
        msg.hidden = false;
        msg.className = 'action-msg err';
        msg.textContent = 'fork_workflow failed: Go payload must be valid JSON';
        setTimeout(() => { msg.hidden = true; }, 5000);
        return;
      }
    } else {
      body.raw_workflow_input_override = $('fork-input-override').value;
    }
  }

  const rawStepOutputOverrides = {};
  for (const [functionId, rawValue] of Object.entries(forkState.stepOutputEdits)) {
    const serialization = forkState.rawStepOutputs[functionId]?.serialization;
    const editorMode = forkState.rawStepOutputs[functionId]?.editor?.mode;
    if (isPythonPickleSerialization(serialization)) {
      if (editorMode !== 'python-value') {
        continue;
      }
      try {
        body.step_output_overrides = body.step_output_overrides || {};
        body.step_output_overrides[functionId] = JSON.parse(rawValue);
      } catch (_) {
        const msg = $('action-msg');
        msg.hidden = false;
        msg.className = 'action-msg err';
        msg.textContent = `fork_workflow failed: Step ${functionId} Python payload editor must be valid JSON`;
        setTimeout(() => { msg.hidden = true; }, 5000);
        return;
      }
      continue;
    }
    if (isGoDbosJsonSerialization(serialization)) {
      try {
        rawStepOutputOverrides[functionId] = encodeGoDbosJsonPayload(rawValue);
      } catch (_) {
        const msg = $('action-msg');
        msg.hidden = false;
        msg.className = 'action-msg err';
        msg.textContent = `fork_workflow failed: Step ${functionId} Go payload must be valid JSON`;
        setTimeout(() => { msg.hidden = true; }, 5000);
        return;
      }
      continue;
    }
    rawStepOutputOverrides[functionId] = rawValue;
  }
  if (Object.keys(rawStepOutputOverrides).length > 0) {
    body.raw_step_output_overrides = rawStepOutputOverrides;
  }

  // Always go through the staged-fork path so the websocket cancel + edit
  // semantics are consistent. If no edits/overrides are present, send an
  // empty step_output_overrides marker to force the staged path.
  if (!body.raw_workflow_input_override && !body.raw_step_output_overrides) {
    body.step_output_overrides = {};
  }
  body.cancel_original_if_active = forkState.sourceIsActive && $('fork-cancel-original').checked;

  try {
    const response = await callApi('/api/control-plane/fork', body, `fork_workflow (${mode})`);
    if (mode === 'stage') {
      showForkPostStage(response.response);
      return;
    }
    closeForkModal();
  } catch (_) {}
}

$('fork-submit-btn').addEventListener('click', () => submitForkWithMode('stage'));
$('fork-run-btn').addEventListener('click', () => submitForkWithMode('run'));

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
let readyForWorkflowPolling = false;
let stateRefreshInFlight = null;
let workflowRefreshInFlight = null;

async function refreshState() {
  if (stateRefreshInFlight) {
    return stateRefreshInFlight;
  }

  stateRefreshInFlight = (async () => {
  try {
    const res   = await fetch('/api/control-plane/state');
    if (!res.ok) throw new Error(res.statusText);
    const state = await res.json();

    pollFailed = false;

    renderConnection(state);
    renderSession(state);
    renderRequests(state.requests ?? []);
    renderWorkflows(state.last_list_workflows_output ?? []);

    const ready = state.session?.status === 'ready';
    readyForWorkflowPolling = ready;
    ['btn-list-workflows', 'btn-list-queued', 'btn-recovery'].forEach(id => {
      $(id).disabled = !ready;
    });

    $('poll-clock').textContent = new Date().toLocaleTimeString('en-GB', { hour12: false });
  } catch (err) {
    if (!pollFailed) {
      pollFailed = true;
      console.error('State poll failed:', err);
    }
  } finally {
    stateRefreshInFlight = null;
  }
  })();

  return stateRefreshInFlight;
}

async function refreshWorkflows({ hardRefresh = false } = {}) {
  if (!readyForWorkflowPolling) {
    return;
  }
  if (workflowRefreshInFlight) {
    return workflowRefreshInFlight;
  }

  workflowRefreshInFlight = (async () => {
    const msg = $('action-msg');
    if (hardRefresh) {
      msg.hidden = false;
      msg.className = 'action-msg';
      msg.textContent = 'hard refresh…';
    }

    try {
      const res = await fetch('/api/control-plane/list-workflows', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || res.statusText);

      await refreshState();

      if (hardRefresh) {
        msg.className = 'action-msg ok';
        msg.textContent = `hard refresh → ${json.status || 'sent'}`;
        setTimeout(() => { msg.hidden = true; }, 3000);
      }

      return json;
    } catch (err) {
      if (hardRefresh) {
        msg.className = 'action-msg err';
        msg.textContent = `hard refresh failed: ${err.message}`;
        setTimeout(() => { msg.hidden = true; }, 5000);
      } else {
        console.error('Workflow poll failed:', err);
      }
      throw err;
    } finally {
      workflowRefreshInFlight = null;
    }
  })();

  return workflowRefreshInFlight;
}

$('btn-list-workflows').addEventListener('click', () =>
  refreshWorkflows({ hardRefresh: true }),
);

async function refresh() {
  await refreshState();
  if (readyForWorkflowPolling) {
    try {
      await refreshWorkflows();
    } catch (_) {}
  }
}

refresh();
setInterval(refresh, 5000);
