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
          <button class="btn-sm" onclick="doRestart('${escAttr(id)}')">restart</button>
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
  if (!confirm(`Restart workflow ${id} from step 1?`)) return;
  try {
    await callApi('/api/control-plane/restart', { workflow_id: id }, 'restart');
  } catch (_) {}
};

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
  if (e.key === 'Escape') closeInspect();
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
