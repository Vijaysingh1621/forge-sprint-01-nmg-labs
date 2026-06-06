/* app.js — SEO Command Center live cockpit. Plain DOM + SSE, no build step. */
'use strict';

const $ = (id) => document.getElementById(id);
let totals = { High: 0, Medium: 0, Low: 0, total: 0 };
let timerInterval = null;
let startTime = null;
let progress = 0;

// ── Timer ──────────────────────────────────────────────────────────────────
function startTimer() {
  startTime = Date.now();
  clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    $('timer').textContent = elapsed + 's';
  }, 100);
}
function stopTimer() {
  clearInterval(timerInterval);
}

// ── Progress bar ───────────────────────────────────────────────────────────
function setProgress(pct) {
  $('progress-inner').style.width = Math.min(100, pct) + '%';
}

// ── Stage indicator ────────────────────────────────────────────────────────
const STAGES = ['loading', 'detecting', 'fixing', 'reporting'];
function setStage(stage, msg) {
  STAGES.forEach(s => {
    const el = $('step-' + s);
    if (!el) return;
    el.classList.remove('active', 'done');
  });
  const idx = STAGES.indexOf(stage);
  STAGES.forEach((s, i) => {
    const el = $('step-' + s);
    if (!el) return;
    if (i < idx) el.classList.add('done');
    else if (i === idx) el.classList.add('active');
  });
  if (stage === 'done') {
    STAGES.forEach(s => { const el = $('step-' + s); if (el) el.classList.add('done'); });
  }
  if (stage === 'error') {
    STAGES.forEach(s => { const el = $('step-' + s); if (el) el.classList.remove('active', 'done'); });
  }
  if (msg) $('stage-msg').textContent = msg;
}

// ── Logging ────────────────────────────────────────────────────────────────
function log(msg, cls = '') {
  const l = $('log');
  if (l.querySelector('.empty')) l.innerHTML = '';
  const d = document.createElement('div');
  d.textContent = '› ' + msg;
  if (cls) d.className = cls;
  l.appendChild(d);
  l.scrollTop = l.scrollHeight;
}

// ── Issue table ────────────────────────────────────────────────────────────
function addIssue(i) {
  const tb = $('tbody');
  if (tb.querySelector('.empty')) tb.innerHTML = '';
  const tr = document.createElement('tr');
  tr.innerHTML =
    `<td><span class="sev ${i.severity.toLowerCase()}">${i.severity}</span></td>` +
    `<td style="font-family:monospace;font-size:11.5px;color:#a78bfa">${i.type}</td>` +
    `<td style="text-align:right;font-weight:600">${i.count}</td>`;
  tb.appendChild(tr);
  totals[i.severity] = (totals[i.severity] || 0) + 1;
  totals.total++;
  $('c-total').textContent = totals.total;
  $('c-high').textContent  = totals.High;
  $('c-med').textContent   = totals.Medium;
  $('c-low').textContent   = totals.Low;
  progress = Math.min(85, progress + 5);
  setProgress(progress);
}

// ── Recommendations ────────────────────────────────────────────────────────
function setRecs(recs) {
  const ul = $('recs-list');
  ul.innerHTML = '';
  (recs || []).forEach(r => {
    const li = document.createElement('li');
    li.textContent = r;
    ul.appendChild(li);
  });
  if (!recs || !recs.length) {
    ul.innerHTML = '<li class="empty">No recommendations.</li>';
  }
}

// ── Event handler ──────────────────────────────────────────────────────────
function handle({ event, data }) {
  if (event === 'snapshot') {
    if (data.site) {
      $('site-pill').textContent = '· ' + data.site;
      $('urls-pill').textContent = (data.urls || 0) + ' URLs';
    }
    (data.issues || []).forEach(addIssue);
    if (data.status === 'done' || data.status === 'error') {
      stopTimer();
      setProgress(100);
      $('run-btn').disabled = false;
      $('run-btn').textContent = '▶ Run Again';
    }
    if (data.recommendations) setRecs(data.recommendations);
    const fx = data.fixes || {};
    if (fx.titles) $('c-fixes').textContent = (fx.titles || []).length;
    if (fx.redirect_map) $('c-reds').textContent = (fx.redirect_map || []).length;

  } else if (event === 'loaded') {
    $('site-pill').textContent = '· ' + data.site;
    $('urls-pill').textContent = data.urls + ' URLs';
    $('site-pill').className = 'pill active';
    $('tbody').innerHTML = '';
    $('recs-list').innerHTML = '<li class="empty">Detecting issues…</li>';
    totals = { High: 0, Medium: 0, Low: 0, total: 0 };
    ['c-total','c-high','c-med','c-low'].forEach(id => $(id).textContent = '0');
    setStage('loading', 'Loaded ' + data.urls + ' URLs');
    progress = 15; setProgress(progress);

  } else if (event === 'stage') {
    setStage(data.stage, data.msg);
    const pMap = { loading: 15, detecting: 40, fixing: 75, reporting: 90, done: 100 };
    if (pMap[data.stage]) { progress = pMap[data.stage]; setProgress(progress); }
    if (data.stage === 'done' || data.stage === 'error') {
      stopTimer();
      $('run-btn').disabled = false;
      $('run-btn').textContent = data.stage === 'done' ? '▶ Run Again' : '▶ Retry';
    }

  } else if (event === 'issue') {
    addIssue(data);
    log('Found ' + data.count + ' × ' + data.type);

  } else if (event === 'summary') {
    log('Audit complete: ' + data.total_issues + ' issue types detected');
    setStage('detecting', 'Detected ' + data.total_issues + ' issue types');

  } else if (event === 'fixes') {
    const t = (data.titles || []).length;
    const r = (data.redirect_map || []).length;
    $('c-fixes').textContent = t;
    $('c-reds').textContent  = r;
    log('Fixes ready: ' + t + ' title rewrites, ' + r + ' redirect suggestions');

  } else if (event === 'recommendations') {
    setRecs(data.recommendations);
    log('Recommendations generated (' + (data.recommendations || []).length + ')');

  } else if (event === 'saved') {
    log('report.json saved ✓', 'ok');
    setProgress(98);

  } else if (event === 'exported') {
    $('export-box').innerHTML =
      '<b style="color:#4ade80">report.html written ✓</b><br>' +
      '<span style="color:#6b7280;font-size:12px">Also written: titles_meta_fixes.csv, redirect_map.csv</span>';
    log('All outputs written ✓', 'ok');
    setProgress(100);
    STAGES.forEach(s => { const el = $('step-' + s); if (el) el.classList.add('done'); });
    $('stage-msg').textContent = 'Completed successfully';
    $('run-btn').disabled = false;
    $('run-btn').textContent = '▶ Run Again';
    stopTimer();

  } else if (event === 'log') {
    const cls = data.msg.startsWith('✓') || data.msg.includes('Done') ? 'ok'
              : data.msg.startsWith('Error') ? 'err' : '';
    log(data.msg, cls);
  }
}

// ── Run Audit button ───────────────────────────────────────────────────────
function runAudit() {
  const btn = $('run-btn');
  btn.disabled = true;
  btn.textContent = 'Running…';
  $('log').innerHTML = '';
  $('export-box').innerHTML = '<span class="empty">report.html will be ready when the run finishes.</span>';
  $('tbody').innerHTML = '<tr><td colspan="3" class="empty">Loading…</td></tr>';
  $('recs-list').innerHTML = '<li class="empty">Generating recommendations…</li>';
  totals = { High: 0, Medium: 0, Low: 0, total: 0 };
  ['c-total','c-high','c-med','c-low','c-fixes','c-reds'].forEach(id => $(id).textContent = '0');
  $('site-pill').className = 'pill';
  $('site-pill').textContent = 'starting…';
  progress = 5; setProgress(progress);
  setStage('loading', 'Starting audit…');
  startTimer();

  fetch('/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ export_dir: 'sample-export' })
  })
    .then(r => r.json())
    .then(d => {
      if (!d.started) {
        log('Failed to start: ' + (d.error || 'unknown error'), 'err');
        btn.disabled = false; btn.textContent = '▶ Run Audit';
        stopTimer();
      }
    })
    .catch(e => {
      log('Network error: ' + e, 'err');
      btn.disabled = false; btn.textContent = '▶ Run Audit';
      stopTimer();
    });
}

// ── SSE connection ─────────────────────────────────────────────────────────
const es = new EventSource('/events');
es.onmessage = (m) => { try { handle(JSON.parse(m.data)); } catch (e) {} };
es.onerror = () => {
  $('site-pill').textContent = 'disconnected';
  $('site-pill').className = 'pill';
  setTimeout(() => location.reload(), 3000);
};
