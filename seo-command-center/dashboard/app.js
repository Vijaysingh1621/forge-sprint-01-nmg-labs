/* app.js — SEO Command Center live cockpit. Plain DOM + SSE, no build step. */
const $ = (id) => document.getElementById(id);
let totals = { High: 0, Medium: 0, Low: 0, total: 0 };
let progress = 0;

function log(msg, type = "") {
  const l = $("log"); if (l.querySelector(".empty")) l.innerHTML = "";
  const d = document.createElement("div");
  d.textContent = "› " + msg;
  if (type) d.className = type;
  l.appendChild(d); l.scrollTop = l.scrollHeight;
}

function setProgress(pct) {
  const bar = $("progress-bar"), inner = $("progress-inner");
  if (pct > 0) { bar.style.display = "block"; inner.style.width = pct + "%"; }
  else { bar.style.display = "none"; inner.style.width = "0%"; }
}

function addIssue(i) {
  const tb = $("tbody"); if (tb.querySelector(".empty")) tb.innerHTML = "";
  const tr = document.createElement("tr");
  tr.innerHTML = `<td><span class="sev ${i.severity.toLowerCase()}">${i.severity}</span></td>
                  <td>${i.type}</td><td>${i.count}</td>`;
  tb.appendChild(tr);
  totals[i.severity] = (totals[i.severity] || 0) + 1; totals.total++;
  $("c-total").textContent = totals.total; $("c-high").textContent = totals.High;
  $("c-med").textContent = totals.Medium; $("c-low").textContent = totals.Low;
  // Update progress (each issue adds to progress bar up to 90%)
  progress = Math.min(90, progress + 6);
  setProgress(progress);
}

function handle({ event, data }) {
  if (event === "snapshot") {
    if (data.site) { $("meta").textContent = "· " + data.site; $("urls").textContent = (data.urls||0) + " URLs"; }
    (data.issues || []).forEach(addIssue);
    if (data.status === "done") { setProgress(100); setTimeout(() => setProgress(0), 2000); }
  } else if (event === "loaded") {
    $("meta").textContent = "running · " + data.site; $("urls").textContent = data.urls + " URLs";
    log(`Loaded ${data.urls} URLs from ${data.site}`); $("tbody").innerHTML = "";
    totals = { High:0, Medium:0, Low:0, total:0 };
    $("c-total").textContent = $("c-high").textContent = $("c-med").textContent = $("c-low").textContent = "0";
    progress = 10; setProgress(progress);
  } else if (event === "issue") {
    addIssue(data); log(`Found ${data.count} × ${data.type}`);
  } else if (event === "summary") {
    log(`Audit complete: ${data.total_issues} issue types`);
    $("meta").textContent = "done · " + (data.site || "");
    progress = 95; setProgress(progress);
  } else if (event === "fixes") {
    log(`Fixes ready: ${(data.titles||[]).length} titles, ${(data.redirect_map||[]).length} redirects`);
  } else if (event === "exported") {
    $("export").innerHTML = "<b>report.html written ✓</b><br><span style='color:#c8c5be;font-size:12px'>Open outputs/report.html to view the full audit report.</span>";
    log("Done!", "ok");
    setProgress(100); setTimeout(() => setProgress(0), 2000);
    $("run-btn").disabled = false; $("run-btn").textContent = "▶ Run Again";
  } else if (event === "saved") {
    log("report.json saved");
  } else if (event === "log") {
    log(data.msg, data.msg.startsWith("Error") ? "err" : data.msg.includes("Done") ? "ok" : "");
  } else if (event === "recommendations") {
    log(`Recommendations: ${(data.recommendations||[]).join(" | ")}`);
  }
}

function runAudit() {
  const btn = $("run-btn");
  btn.disabled = true; btn.textContent = "Running…";
  $("meta").textContent = "starting…";
  $("tbody").innerHTML = "<tr><td colspan='3' class='empty'>Loading data…</td></tr>";
  $("log").innerHTML = "";
  $("export").innerHTML = "<span class='empty'>report.html will be ready when the run finishes.</span>";
  totals = { High:0, Medium:0, Low:0, total:0 };
  $("c-total").textContent = $("c-high").textContent = $("c-med").textContent = $("c-low").textContent = "0";
  progress = 5; setProgress(progress);

  fetch("/run", { method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ export_dir: "sample-export" }) })
    .then(r => r.json())
    .then(d => { if (!d.started) { log("Failed to start: " + (d.error||"unknown"), "err"); btn.disabled = false; btn.textContent = "▶ Run Audit"; } })
    .catch(e => { log("Error: " + e, "err"); btn.disabled = false; btn.textContent = "▶ Run Audit"; });
}

const es = new EventSource("/events");
es.onmessage = (m) => { try { handle(JSON.parse(m.data)); } catch (e) {} };
es.onerror = () => { $("meta").textContent = "disconnected"; };
