const GUIDE_KEY = 'fim-guide-v1';
let lastAlertCount = 0;
let demoPath = '';

async function api(url, opts) {
  const res = await fetch(url, opts);
  return res.json();
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s ?? '';
  return d.innerHTML;
}

function truncHash(h) {
  if (!h) return '—';
  return h.slice(0, 12) + '…';
}

function getGuideState() {
  try { return JSON.parse(localStorage.getItem(GUIDE_KEY) || '{}'); } catch { return {}; }
}

function setGuideStep(n, done = true) {
  const s = getGuideState();
  if (done) s[n] = true;
  localStorage.setItem(GUIDE_KEY, JSON.stringify(s));
  renderGuide();
}

function renderGuide() {
  const s = getGuideState();
  let done = 0;
  document.querySelectorAll('.guide-steps li').forEach(li => {
    const n = +li.dataset.step;
    const complete = !!s[n];
    li.classList.toggle('done', complete);
    if (complete) done++;
  });
  document.getElementById('guide-progress').textContent = `${done} / 8 steps`;
}

function updateWizard(hasBaseline, monitoring, hasAlerts) {
  document.querySelectorAll('.wizard-step').forEach(el => {
    el.classList.remove('active', 'complete');
  });
  const w1 = document.querySelector('.wizard-step[data-w="1"]');
  const w2 = document.querySelector('.wizard-step[data-w="2"]');
  const w3 = document.querySelector('.wizard-step[data-w="3"]');
  if (hasBaseline) { w1.classList.add('complete'); w2.classList.add('active'); }
  else w1.classList.add('active');
  if (monitoring) { w2.classList.add('complete'); w3.classList.add('active'); }
  if (hasAlerts) w3.classList.add('complete');
}

function formatChangeTime(a) {
  return a.time_display || a.time || '—';
}

function renderAlerts(alerts) {
  const list = document.getElementById('alert-list');
  const empty = document.getElementById('alert-empty');

  if (alerts.length > lastAlertCount && alerts.length > 0) {
    list.classList.add('flash-new');
    setTimeout(() => list.classList.remove('flash-new'), 800);
    if (alerts.length >= 1) setGuideStep(6);
  }
  lastAlertCount = alerts.length;

  if (!alerts.length) {
    list.classList.add('hidden');
    empty.classList.remove('hidden');
    if (monitor_state_monitoring()) {
      empty.querySelector('p:last-child').textContent =
        'Monitoring active — no changes detected. Edit sample.txt to test.';
    }
    return;
  }

  empty.classList.add('hidden');
  list.classList.remove('hidden');
  list.innerHTML = alerts.map(a => {
    const hashDiff = a.type === 'MODIFIED' && a.hash_before && a.hash_after
      ? `<div class="hash-diff"><span>Before:</span> <code>${truncHash(a.hash_before)}</code><br><span>After:</span> <code>${truncHash(a.hash_after)}</code></div>`
      : a.hash_before ? `<div class="hash-diff"><span>Was:</span> <code>${truncHash(a.hash_before)}</code></div>`
      : a.hash_after ? `<div class="hash-diff"><span>Now:</span> <code>${truncHash(a.hash_after)}</code></div>` : '';
    return `
      <li class="timeline-item type-${a.type}">
        <div class="timeline-dot"></div>
        <div class="timeline-body">
          <span class="alert-type type-${a.type}">${a.type}</span>
          <div class="alert-path">${esc(a.path)}</div>
          <div class="alert-time-block"><strong>Changed at:</strong> ${esc(formatChangeTime(a))}</div>
          ${a.detail ? `<div class="alert-detail">${esc(a.detail)}</div>` : ''}
          ${hashDiff}
        </div>
      </li>`;
  }).join('');
}

let _monitoring = false;
function monitor_state_monitoring() { return _monitoring; }

function renderFileTree(files) {
  const body = document.getElementById('file-tree-body');
  if (!files || !files.length) {
    body.innerHTML = '<tr><td colspan="4" class="empty-cell">Create a baseline to see files</td></tr>';
    return;
  }
  body.innerHTML = files.map(f => `
    <tr class="f-${f.status}">
      <td class="fname">${esc(f.path)}</td>
      <td><span class="fstatus ${f.status}">${f.status}</span></td>
      <td class="mono">${truncHash(f.hash || f.baseline_hash)}</td>
      <td>${f.size != null ? f.size + ' B' : '—'}</td>
    </tr>`).join('');
}

function renderIntegrity(integrity) {
  const wrap = document.getElementById('integrity-wrap');
  if (!integrity || !integrity.total) {
    wrap.classList.add('hidden');
    return;
  }
  wrap.classList.remove('hidden');
  const score = integrity.score;
  document.getElementById('integrity-pct').textContent = score + '%';
  const ring = document.getElementById('integrity-ring');
  ring.style.setProperty('--pct', score);
  ring.classList.toggle('score-warn', score < 100 && score >= 80);
  ring.classList.toggle('score-bad', score < 80);

  const cap = document.getElementById('integrity-caption');
  if (score === 100) cap.textContent = 'All files match baseline';
  else cap.textContent = `${integrity.modified} modified · ${integrity.missing} missing · ${integrity.extra} new`;
}

function renderDashboard(data) {
  document.getElementById('dash-files').textContent = data.integrity?.total || data.file_count || 0;
  const score = data.integrity?.score ?? 100;
  const scoreEl = document.getElementById('dash-score');
  scoreEl.textContent = score + '%';
  scoreEl.className = score === 100 ? 'score-ok' : score >= 80 ? 'score-warn' : 'score-bad';

  const statusEl = document.getElementById('dash-status');
  if (data.monitoring) {
    statusEl.textContent = 'Monitoring';
    statusEl.className = 'status-live';
    document.getElementById('pulse-dot').classList.add('live');
  } else {
    statusEl.textContent = data.file_count ? 'Ready' : 'Idle';
    statusEl.className = 'status-idle';
    document.getElementById('pulse-dot').classList.remove('live');
  }

  document.getElementById('dash-last').textContent = data.last_check
    ? new Date(data.last_check).toLocaleTimeString() : '—';
  document.getElementById('dash-alerts').textContent = data.alert_count || 0;

  renderIntegrity(data.integrity);
  renderFileTree(data.files);
  _monitoring = data.monitoring;
  updateWizard(!!data.file_count, data.monitoring, (data.alert_count || 0) > 0);
}

async function refreshAll() {
  const [status, alerts, hist] = await Promise.all([
    api('/api/status'),
    api('/api/alerts'),
    api('/api/baseline/history'),
  ]);

  if (status.watch_path) {
    document.getElementById('dir-path').value = status.watch_path;
  }
  renderDashboard(status);
  renderAlerts(alerts.alerts);

  if (status.integrity?.score < 100 && status.monitoring) {
    setGuideStep(5);
  }

  const hlist = document.getElementById('history-list');
  if (hist.history?.length) {
    hlist.innerHTML = hist.history.map(h =>
      `<li><strong>${esc(h.label)}</strong><br><span class="mono">${esc(h.created?.slice(0, 19) || '')}</span> · ${h.file_count} files</li>`
    ).join('');
  }

  if (status.monitoring) {
    document.getElementById('start-btn').disabled = true;
    document.getElementById('stop-btn').disabled = false;
  }
}

document.getElementById('demo-create-btn').addEventListener('click', async () => {
  const data = await api('/api/demo/create', { method: 'POST' });
  demoPath = data.path;
  document.getElementById('dir-path').value = data.path;
  document.getElementById('baseline-status').textContent = data.message;
  setGuideStep(1);
});

document.getElementById('copy-path-btn').addEventListener('click', async () => {
  if (!demoPath) {
    const d = await api('/api/demo/path');
    demoPath = d.path;
  }
  document.getElementById('dir-path').value = demoPath;
  try {
    await navigator.clipboard.writeText(demoPath);
    alert('Path copied! Paste it in the watch field if needed.');
  } catch {
    alert('Path: ' + demoPath);
  }
  setGuideStep(2);
});

document.getElementById('use-demo-btn').addEventListener('click', async () => {
  const d = await api('/api/demo/path');
  demoPath = d.path;
  document.getElementById('dir-path').value = d.path;
  setGuideStep(2);
});

document.getElementById('baseline-btn').addEventListener('click', async () => {
  const path = document.getElementById('dir-path').value.trim();
  const data = await api('/api/baseline', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (data.error) return alert(data.error);
  document.getElementById('baseline-status').textContent =
    `Baseline created: ${data.file_count} files hashed`;
  setGuideStep(3);
  lastAlertCount = 0;
  await refreshAll();
});

document.getElementById('start-btn').addEventListener('click', async () => {
  const data = await api('/api/monitor/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      path: document.getElementById('dir-path').value.trim(),
      interval: +document.getElementById('interval').value,
    }),
  });
  if (data.error) return alert(data.error);
  setGuideStep(4);
  await refreshAll();
});

document.getElementById('stop-btn').addEventListener('click', async () => {
  await api('/api/monitor/stop', { method: 'POST' });
  document.getElementById('start-btn').disabled = false;
  document.getElementById('stop-btn').disabled = true;
  await refreshAll();
});

document.getElementById('scan-btn').addEventListener('click', async () => {
  const data = await api('/api/scan-now', { method: 'POST' });
  if (data.error) return alert(data.error);
  await refreshAll();
});

document.getElementById('update-baseline-btn').addEventListener('click', async () => {
  if (!confirm('Accept current files as the new trusted baseline? Alerts will be cleared.')) return;
  const data = await api('/api/baseline/update', { method: 'POST' });
  if (data.error) return alert(data.error);
  setGuideStep(8);
  lastAlertCount = 0;
  await refreshAll();
});

document.getElementById('export-csv').addEventListener('click', async () => {
  const { alerts } = await api('/api/alerts');
  if (!alerts.length) return alert('No alerts to export');
  setGuideStep(7);
  const header = 'type,path,changed_at,detail,hash_before,hash_after\n';
  const rows = alerts.map(a =>
    [a.type, a.path, formatChangeTime(a), a.detail || '', a.hash_before || '', a.hash_after || '']
      .map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')
  ).join('\n');
  const blob = new Blob([header + rows], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'fim-alerts.csv';
  a.click();
});

renderGuide();
api('/api/demo/path').then(d => { demoPath = d.path; });
refreshAll();
setInterval(refreshAll, 3000);
