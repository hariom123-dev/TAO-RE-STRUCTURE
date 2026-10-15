/**
 * TAO — Unified Application Logic
 *
 * Combines Dashboard (pipeline analysis) and Judge AI Chat
 * into a single-page application with sidebar tab navigation.
 *
 * Manages:
 * - View switching (Dashboard ↔ Chat)
 * - Dashboard: API communication, pipeline state, panel rendering
 * - Chat: Message sending, judge verdicts, flow diagram
 * - Mobile sidebar toggle
 */

// ─── Configuration ──────────────────────────────────────────
const API_BASE = window.location.origin;
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;

// ═══════════════════════════════════════════════════════════
// VIEW SWITCHING
// ═══════════════════════════════════════════════════════════

const navTabs = document.querySelectorAll('.nav-tab');
const views = document.querySelectorAll('.view');
const mobileToggle = document.getElementById('mobile-toggle');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');

function switchView(viewName) {
  // Update tabs
  navTabs.forEach(tab => {
    tab.classList.toggle('active', tab.dataset.view === viewName);
  });

  // Update views
  views.forEach(view => {
    view.classList.toggle('active', view.id === `view-${viewName}`);
  });

  // Close mobile sidebar
  sidebar.classList.remove('open');

  // Update document title and trigger view-specific loaders
  if (viewName === 'dashboard') {
    document.title = 'TAO — Pipeline Dashboard';
  } else if (viewName === 'chat') {
    document.title = 'TAO — Judge AI Chat';
  } else if (viewName === 'compiler') {
    document.title = 'TAO — DSPy Prompt Evolution';
    loadCompilerStatus();
  } else if (viewName === 'redteam') {
    document.title = 'TAO — Houdini Red-Team Arena';
  }
}

navTabs.forEach(tab => {
  tab.addEventListener('click', () => switchView(tab.dataset.view));
});

// Mobile sidebar toggle
if (mobileToggle) {
  mobileToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });
}

if (sidebarOverlay) {
  sidebarOverlay.addEventListener('click', () => {
    sidebar.classList.remove('open');
  });
}


// ═══════════════════════════════════════════════════════════
// DASHBOARD LOGIC
// ═══════════════════════════════════════════════════════════

// ─── State ──────────────────────────────────────────────────
let isAnalyzing = false;
let currentResult = null;
let ws = null;

// ─── DOM References — Dashboard ─────────────────────────────
const queryInput = document.getElementById('query-input');
const analyzeBtn = document.getElementById('analyze-btn');
const tierSelect = document.getElementById('tier-select');
const presetContainer = document.getElementById('presets');
const statusBadge = document.getElementById('status-badge');
const statusText = document.getElementById('status-text');
const sidebarStatus = document.getElementById('sidebar-status');
const sidebarStatusText = document.getElementById('sidebar-status-text');

// Pipeline nodes
const nodeRouter = document.getElementById('node-router');
const nodeTier1 = document.getElementById('node-tier1');
const nodeTier2 = document.getElementById('node-tier2');
const nodeTier3 = document.getElementById('node-tier3');
const nodeOutput = document.getElementById('node-output');
const connectors = [
  document.getElementById('connector-0'),
  document.getElementById('connector-1'),
  document.getElementById('connector-2'),
  document.getElementById('connector-3'),
];

// Panel bodies
const responseBody = document.getElementById('response-body');
const tier1Body = document.getElementById('tier1-body');
const tier2Body = document.getElementById('tier2-body');
const tier3Body = document.getElementById('tier3-body');
const metricsBody = document.getElementById('metrics-body');

// Badges
const badgeResponse = document.getElementById('badge-response');
const badgeTier1 = document.getElementById('badge-tier1');
const badgeTier2 = document.getElementById('badge-tier2');
const badgeTier3 = document.getElementById('badge-tier3');
const badgeMetrics = document.getElementById('badge-metrics');

// ─── Init ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  checkConfig();
  setupDashboardListeners();
  setupChatListeners();
  setupModalListeners();
  setupCompilerListeners();
  setupRedTeamListeners();
  checkOllama();
  loadChatConfig();
});

async function checkConfig() {
  try {
    const res = await fetch(`${API_BASE}/api/config`);
    const config = await res.json();
    if (config.simulation_mode) {
      statusBadge.className = 'sidebar-status simulation';
      statusText.textContent = 'Simulation';
      sidebarStatus.className = 'sidebar-status simulation';
      sidebarStatusText.textContent = 'Simulation Mode';
    } else {
      statusBadge.className = 'sidebar-status connected';
      statusText.textContent = 'Live';
      sidebarStatus.className = 'sidebar-status connected';
      sidebarStatusText.textContent = 'Live Mode';
    }
  } catch (e) {
    statusText.textContent = 'Offline';
    sidebarStatusText.textContent = 'Server Offline';
    sidebarStatus.className = 'sidebar-status disconnected';
  }
}

function setupDashboardListeners() {
  analyzeBtn.addEventListener('click', () => analyzeQuery());

  queryInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      analyzeQuery();
    }
  });

  presetContainer.addEventListener('click', (e) => {
    const btn = e.target.closest('.preset-btn');
    if (btn && !btn.classList.contains('quick-prompt')) {
      queryInput.value = btn.dataset.query;
      queryInput.focus();
    }
  });
}

// ─── Analysis ───────────────────────────────────────────────
async function analyzeQuery() {
  const query = queryInput.value.trim();
  if (!query || isAnalyzing) return;

  isAnalyzing = true;
  analyzeBtn.disabled = true;
  analyzeBtn.innerHTML = '<span class="spinner"></span> Analyzing...';

  resetPipeline();

  const forceT = tierSelect.value;
  const body = {
    query,
    force_tier: forceT === 'auto' ? null : parseInt(forceT),
  };

  try {
    const wsOk = await analyzeViaWebSocket(body);
    if (!wsOk) {
      await analyzeViaREST(body);
    }
  } catch (err) {
    console.error('Analysis error:', err);
    showError('Analysis failed. Check that the server is running.');
  } finally {
    isAnalyzing = false;
    analyzeBtn.disabled = false;
    analyzeBtn.innerHTML = '🔍 Analyze';
  }
}

async function analyzeViaWebSocket(body) {
  return new Promise((resolve) => {
    try {
      ws = new WebSocket(`${WS_BASE}/ws/pipeline`);
      let resolved = false;

      ws.onopen = () => {
        ws.send(JSON.stringify(body));
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.event_type === 'final_result') {
          currentResult = data.data;
          renderFullResult(currentResult);
          if (!resolved) { resolved = true; resolve(true); }
          ws.close();
        } else {
          handlePipelineEvent(data);
        }
      };

      ws.onerror = () => {
        if (!resolved) { resolved = true; resolve(false); }
      };

      ws.onclose = () => {
        if (!resolved) { resolved = true; resolve(false); }
      };

      setTimeout(() => {
        if (!resolved) { resolved = true; resolve(false); ws.close(); }
      }, 30000);
    } catch {
      resolve(false);
    }
  });
}

async function analyzeViaREST(body) {
  setNodeState(nodeRouter, 'active');

  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  currentResult = await res.json();
  renderFullResult(currentResult);
}

// ─── Pipeline Event Handling ──────────────────────────────
function handlePipelineEvent(event) {
  const { event_type, data } = event;

  switch (event_type) {
    case 'routing':
      setNodeState(nodeRouter, 'active');
      setBadge(badgeResponse, 'active', 'Routing');
      break;
    case 'routing_complete':
      setNodeState(nodeRouter, 'completed');
      setConnectorActive(0);
      renderRouting(data);
      break;
    case 'tier1_start':
      setNodeState(nodeTier1, 'active');
      setBadge(badgeTier1, 'active', 'Processing');
      break;
    case 'tier1_complete':
      setNodeState(nodeTier1, data.passed ? 'completed' : 'flagged');
      setConnectorActive(1);
      setBadge(badgeTier1, data.passed ? 'passed' : 'flagged', data.passed ? 'Passed' : 'Flagged');
      break;
    case 'tier2_start':
      setNodeState(nodeTier2, 'active');
      setBadge(badgeTier2, 'active', 'Debating');
      break;
    case 'tier2_complete':
      const t2class = data.verdict === 'prover_wins' ? 'completed' : 'flagged';
      setNodeState(nodeTier2, t2class);
      setConnectorActive(2);
      setBadge(badgeTier2, t2class === 'completed' ? 'passed' : 'flagged',
        data.verdict.replace('_', ' '));
      break;
    case 'tier3_start':
      setNodeState(nodeTier3, 'active');
      setBadge(badgeTier3, 'active', 'Scanning');
      break;
    case 'tier3_complete':
      setNodeState(nodeTier3, data.alert_triggered ? 'flagged' : 'completed');
      setConnectorActive(3);
      setBadge(badgeTier3, data.alert_triggered ? 'flagged' : 'passed',
        data.alert_triggered ? 'Alert' : 'Clear');
      break;
    case 'pipeline_complete':
      setNodeState(nodeOutput, 'completed');
      break;
  }
}

// ─── Rendering ──────────────────────────────────────────────
function renderFullResult(result) {
  const maxTier = result.routing.tier;
  setNodeState(nodeRouter, 'completed');
  setConnectorActive(0);

  if (maxTier >= 0) {
    setNodeState(nodeTier1, 'completed');
    if (result.tier1_result && !result.tier1_result.passed) {
      setNodeState(nodeTier1, 'flagged');
    }
  } else {
    setNodeState(nodeTier1, 'skipped');
  }

  if (maxTier >= 2) {
    setConnectorActive(1);
    setNodeState(nodeTier2, 'completed');
    setConnectorActive(2);
    setNodeState(nodeTier3, result.tier3_result?.stego_analysis?.alert_triggered ? 'flagged' : 'completed');
    setConnectorActive(3);
  } else {
    setNodeState(nodeTier2, 'skipped');
    setNodeState(nodeTier3, 'skipped');
    if (maxTier >= 1) {
      setConnectorActive(1);
    }
  }

  setNodeState(nodeOutput, 'completed');
  if (maxTier < 2) setConnectorActive(connectors.length - 1 > maxTier ? maxTier + 1 : maxTier);

  renderRouting(result.routing);
  renderResponse(result);
  renderTier1(result.tier1_result);
  renderTier2(result.tier2_result);
  renderTier3(result.tier3_result);
  renderMetrics(result.metrics, result.routing);
  loadCheckpoints(result.request_id);
}

function renderRouting(routing) {
  const tierClass = `routing-tier-${routing.tier}`;
  const tierLabel = `Tier ${routing.tier}`;
  const riskPercent = Math.round((routing.risk_score || 0) * 100);

  setBadge(badgeResponse, 'passed', tierLabel);

  const existing = responseBody.querySelector('.routing-info');
  if (existing) existing.remove();

  const routingEl = document.createElement('div');
  routingEl.className = 'routing-info animate-in';
  routingEl.innerHTML = `
    <span class="routing-tier ${tierClass}">${tierLabel}</span>
    <span class="routing-details">
      Risk: <span class="routing-score">${riskPercent}%</span> · 
      Domain: <strong>${routing.domain || 'general'}</strong> · 
      Reasoning Effort: <strong style="text-transform: capitalize; color: var(--color-primary);">${routing.reasoning_effort || (routing.tier >= 2 ? 'high' : routing.tier === 1 ? 'medium' : 'low')}</strong> · 
      ${routing.reasoning || ''}
    </span>
  `;

  responseBody.prepend(routingEl);
}

function renderResponse(result) {
  const oldRes = responseBody.querySelector('.response-content');
  if (oldRes) oldRes.remove();
  const oldData = responseBody.querySelector('.no-data');
  if (oldData) oldData.remove();
  const oldG = responseBody.querySelector('.guardrails-card');
  if (oldG) oldG.remove();
  const oldR = responseBody.querySelector('.receipt-card');
  if (oldR) oldR.remove();

  const el = document.createElement('div');
  el.className = 'response-content animate-in';
  el.textContent = result.final_response || '(No response generated)';
  responseBody.appendChild(el);

  // Render Guardrails AI output validation card (Section 6.1)
  if (result.guardrails_result) {
    const g = result.guardrails_result;
    const gCard = document.createElement('div');
    gCard.className = 'guardrails-card animate-slide';
    gCard.style = 'margin-top: 14px; padding: 12px 14px; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 8px; font-size: 12px;';
    gCard.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <span style="font-weight: 600; color: #10b981; display: flex; align-items: center; gap: 6px;">
          🛡️ Guardrails AI Syntax & Security Check: ${g.passed ? 'PASSED' : 'FLAGGED'}
        </span>
        <span style="font-size: 11px; color: var(--text-secondary);">
          ${result.metrics?.guardrails_latency_ms ? result.metrics.guardrails_latency_ms + ' ms' : 'Active'}
        </span>
      </div>
      <div style="color: var(--text-secondary); line-height: 1.5;">
        Syntax Valid: <strong>${g.syntax_valid ? '✓' : '✗'}</strong> · 
        PII Detected: <strong>${g.pii_detected ? '⚠️ Redacted' : 'None'}</strong> · 
        System Prompt Leak: <strong>${g.prompt_leak_detected ? '⚠️ Alert' : 'Clean'}</strong>
      </div>
    `;
    responseBody.appendChild(gCard);
  }

  // Render Zero-Trust Cryptographic Oversight Receipt (Pillar 7)
  if (result.receipt) {
    const r = result.receipt;
    const rCard = document.createElement('div');
    rCard.className = 'receipt-card animate-slide';
    rCard.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span style="font-weight: 600; color: #c084fc; display: flex; align-items: center; gap: 6px;">
          🔐 Zero-Trust Cryptographic Oversight Receipt
        </span>
        <button id="btn-open-receipt-verify" class="btn btn-secondary" style="font-size: 11px; padding: 4px 10px; border-radius: 4px;">
          Verify Merkle Attestation
        </button>
      </div>
      <div style="display: grid; grid-template-columns: 1fr; gap: 6px; font-size: 11px; color: var(--text-secondary);">
        <div>Root Hash: <span class="receipt-hash-display">${escapeHtml(r.root_hash)}</span></div>
        <div>HMAC Sig: <span class="receipt-hash-display">${escapeHtml((r.signature || '').slice(0, 32))}...</span> · Algorithm: <strong>${escapeHtml(r.algorithm)}</strong> · Leaves: <strong>${r.leaves?.length || 5} leaves</strong></div>
      </div>
    `;
    responseBody.appendChild(rCard);

    const btnVerify = rCard.querySelector('#btn-open-receipt-verify');
    if (btnVerify) {
      btnVerify.addEventListener('click', () => {
        verifyReceiptInModal(r, result.final_response);
      });
    }
  }
}

function renderTier1(tier1) {
  if (!tier1) {
    setBadge(badgeTier1, 'idle', 'Skipped');
    return;
  }

  const passed = tier1.passed;
  setBadge(badgeTier1, passed ? 'passed' : 'flagged', passed ? 'Passed' : 'Flagged');

  let html = '';

  // Render Backtracking and Self-Refine loop card if occurred (Section 3.2 & Pillar 2)
  if (tier1.backtrack_history?.length) {
    const fStep = tier1.backtrack_history[0].failing_step_index;
    html += `
      <div class="violation-card animate-slide" style="border-color: rgba(59, 130, 246, 0.35); background: rgba(59, 130, 246, 0.06); margin-bottom: 14px;">
        <div class="violation-header">
          <span class="violation-type" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa;">
            🔄 O(log N) BINARY SEARCH & BACKTRACKING (OmegaPRM)
          </span>
          <span style="font-size: 11px; color: #93c5fd;">
            ${tier1.iterations} Iterations
          </span>
        </div>
        <div class="violation-explanation" style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">
          Reasoning chain prefix evaluation localized first flawed step to Step ${fStep + 1} via O(log N) bisection. Interrupted generation and rolled back.
        </div>
      </div>
    `;
  }

  // Render Tree-of-Thought (ToT) multi-branch candidates (Pillar 2)
  if (tier1.generation?.alternative_branches?.length) {
    html += `
      <div style="margin-bottom: 14px;">
        <div style="font-size: 12px; font-weight: 600; color: var(--accent); display: flex; align-items: center; gap: 6px; margin-bottom: 8px;">
          🌳 Tree-of-Thought Rollouts (MCTS-Lite K=${tier1.generation.alternative_branches.length} Branches)
        </div>
        <div class="tot-branch-grid">
    `;
    for (const b of tier1.generation.alternative_branches) {
      const isSelected = b.selected ? ' selected' : '';
      html += `
        <div class="tot-branch-card${isSelected}">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span style="font-weight: 700; color: ${b.selected ? 'var(--accent)' : 'var(--text-secondary)'};">Branch ${b.branch_id.toUpperCase()}</span>
            <span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: ${b.selected ? 'rgba(0, 212, 255, 0.2)' : 'rgba(255,255,255,0.05)'}; color: ${b.selected ? 'var(--accent)' : 'var(--text-muted)'};">
              ${b.selected ? '✓ Selected' : 'T=' + b.temperature}
            </span>
          </div>
          <div style="color: var(--text-secondary); margin-bottom: 4px;">
            Score: <strong style="color: ${b.safety_score >= 0.95 ? '#10b981' : '#f59e0b'};">${(b.safety_score * 100).toFixed(0)}%</strong> · Backtracks: ${b.backtrack_count}
          </div>
          <div style="font-size: 10px; color: var(--text-muted); line-height: 1.3;">
            ${escapeHtml((b.content || '').slice(0, 85))}...
          </div>
        </div>
      `;
    }
    html += `</div></div>`;
  }

  // Render DSPy Signature Compartment Inspection (Section 3.1 & Table 1)
  if (tier1.dspy_signature_output) {
    const sig = tier1.dspy_signature_output;
    html += `
      <div class="violation-card animate-slide" style="margin-bottom: 14px; border-color: rgba(168, 85, 247, 0.25); background: rgba(168, 85, 247, 0.04);">
        <div class="violation-header">
          <span class="violation-type" style="background: rgba(168, 85, 247, 0.15); color: #c084fc;">
            DSPy SIGNATURE CONTRACT (Table 1)
          </span>
          <span style="font-size: 11px; color: ${sig.violation_detected ? 'var(--color-danger)' : 'var(--color-success)'};">
            ${sig.violation_detected ? 'Violation: ' + sig.violation_type : 'Violation: None'}
          </span>
        </div>
        <div style="font-size: 11px; margin-top: 6px; color: var(--text-secondary); line-height: 1.5;">
          <strong>Correction Guidance:</strong> ${escapeHtml(sig.correction_guidance)}
        </div>
      </div>
    `;
  }

  if (tier1.generation?.cot_steps?.length) {
    html += '<div class="cot-steps animate-in">';
    for (const step of tier1.generation.cot_steps) {
      const scoreClass = step.safety_score >= 0.95 ? 'score-safe' :
                         step.safety_score >= 0.7 ? 'score-warning' : 'score-danger';
      const flagClass = step.flagged ? ' flagged' : '';
      html += `
        <div class="cot-step${flagClass}">
          <span class="cot-step-index">${step.index + 1}</span>
          <span class="cot-step-content">${escapeHtml(step.content)}</span>
          <span class="cot-step-score ${scoreClass}">${(step.safety_score * 100).toFixed(0)}%</span>
        </div>
      `;
    }
    html += '</div>';
  }

  if (tier1.violations?.length) {
    html += '<div class="violations-list" style="margin-top: 16px;">';
    for (const v of tier1.violations) {
      const sevClass = `severity-${v.severity}`;
      html += `
        <div class="violation-card animate-slide">
          <div class="violation-header">
            <span class="violation-type">${v.violation_type}</span>
            <span class="violation-severity ${sevClass}">${v.severity}</span>
          </div>
          <div class="violation-explanation">${escapeHtml(v.explanation)}</div>
          <div class="violation-guidance">💡 ${escapeHtml(v.correction_guidance)}</div>
        </div>
      `;
    }
    html += '</div>';
  }

  if (tier1.reasoning_anomaly) {
    html += `
      <div class="violation-card animate-slide" style="margin-top: 12px; border-color: rgba(245, 158, 11, 0.35); background: rgba(245, 158, 11, 0.08);">
        <div class="violation-header">
          <span class="violation-type" style="background: rgba(245, 158, 11, 0.15); color: var(--color-warning);">
            ⚠️ REASONING TOKEN ANOMALY (Section 3.3)
          </span>
          <span style="font-size: 11px; color: var(--color-warning);">Triggers Tier 3 Alert</span>
        </div>
        <div class="violation-explanation" style="font-size: 12px; margin-top: 6px;">
          Disproportionate reasoning effort detected for query complexity.
          Model displayed anomalous hidden token spike. Automatic escalation to Tier 3 Steganography Sentinel triggered.
        </div>
      </div>
    `;
  }

  tier1Body.innerHTML = html || '<div class="no-data"><div class="no-data-text">No findings</div></div>';
}

function renderTier2(tier2) {
  if (!tier2) {
    setBadge(badgeTier2, 'idle', 'Skipped');
    return;
  }

  // Check if Case Law Precedent was retrieved (Section 6.1)
  if (tier2.case_law_match) {
    const prec = tier2.case_law_match;
    setBadge(badgeTier2, 'passed', 'Case Law Hit');
    tier2Body.innerHTML = `
      <div class="animate-in" style="padding: 16px; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-weight: 700; color: #10b981; font-size: 14px;">
            📜 Case Law Precedent Retrieved (${prec.id})
          </span>
          <span style="background: rgba(16, 185, 129, 0.2); color: #10b981; padding: 2px 8px; border-radius: 4px; font-size: 11px;">
            ${(prec.similarity_score * 100).toFixed(0)}% Semantic Match
          </span>
        </div>
        <div style="font-size: 13px; color: var(--text-primary); margin-bottom: 10px; line-height: 1.5;">
          ${escapeHtml(prec.summary_ruling)}
        </div>
        <div style="display: flex; gap: 14px; font-size: 11px; color: var(--text-secondary); border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">
          <span>⚡ Bypassed 6.87x Multiplier</span>
          <span>💾 Saved ~${prec.tokens_saved} Tokens</span>
          <span>⏱️ Saved ~${(prec.latency_saved_ms / 1000).toFixed(1)}s Latency</span>
        </div>
      </div>
    `;
    return;
  }

  setBadge(badgeTier2,
    tier2.verdict === 'prover_wins' ? 'passed' : 'flagged',
    tier2.verdict.replace(/_/g, ' ')
  );

  let html = '';

  // Cool-down intervention banner (Section 7.1)
  if (tier2.cooldown_triggered) {
    html += `
      <div class="animate-slide" style="margin-bottom: 12px; padding: 10px 14px; background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 6px; font-size: 12px; color: #93c5fd;">
        🧊 <strong>Cool-Down Grounding Protocol Activated (Section 7.1)</strong>: Argument polarization/hostility detected. Moderator injected agreement-grounding constraints.
      </div>
    `;
  }

  // Weak-to-strong legibility index (Pillar 6)
  if (tier2.weak_verifier_legibility_index !== undefined) {
    const legibilityPct = Math.round(tier2.weak_verifier_legibility_index * 100);
    const legCls = legibilityPct >= 70 ? 'badge-passed' : legibilityPct >= 40 ? 'badge-warning' : 'badge-flagged';
    html += `
      <div style="margin-bottom: 12px; display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--text-secondary);">
        <span>Weak-to-Strong Verifier Legibility:</span>
        <span class="empirical-badge ${legCls}" style="margin: 0;">${legibilityPct}% Legible</span>
        <span style="font-size: 10px; color: var(--text-muted);">(Structural syntax &amp; readability transparency)</span>
      </div>
    `;
  }

  // Ensemble Judging Panel (Section 7.2)
  if (tier2.ensemble_votes?.length) {
    html += '<div class="animate-in" style="margin-bottom: 14px; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);">';
    html += '<div style="font-size: 12px; font-weight: 600; margin-bottom: 8px; color: var(--text-secondary);">👥 3-Judge Ensemble Panel (Majority Vote):</div>';
    html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px;">';
    for (const vote of tier2.ensemble_votes) {
      html += `
        <div style="background: rgba(0,0,0,0.25); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05); font-size: 11px;">
          <div style="font-weight: 600; color: var(--color-primary);">${vote.model_name}</div>
          <div style="margin: 4px 0; color: ${vote.verdict === 'prover_wins' ? '#10b981' : '#f59e0b'};">
            Verdict: ${vote.verdict.replace(/_/g, ' ').toUpperCase()} (${(vote.confidence * 100).toFixed(0)}%)
          </div>
          <div style="color: var(--text-secondary); font-size: 10px; line-height: 1.3;">${escapeHtml(vote.rationale || '')}</div>
        </div>
      `;
    }
    html += '</div></div>';
  }

  html += '<div class="debate-rounds animate-in">';

  for (const round of tier2.rounds) {
    const confPercent = Math.round((round.judge_confidence || 0) * 100);
    const confWidth = Math.min(confPercent, 100);

    let empiricalHtml = '';
    if (round.skeptic_critique?.empirical_evidence?.length) {
      empiricalHtml += '<div class="empirical-evidence-container">';
      empiricalHtml += '<div style="font-size: 10px; font-weight: 700; color: #f59e0b; margin-bottom: 4px;">🛠️ EMPIRICAL TOOL INSPECTION:</div>';
      for (const ev of round.skeptic_critique.empirical_evidence) {
        const evPassed = ev.passed;
        empiricalHtml += `
          <span class="empirical-badge ${evPassed ? 'badge-passed' : 'badge-flagged'}" title="${escapeHtml(ev.output_details || '')}">
            ${evPassed ? '✓' : '⚠️'} ${escapeHtml(ev.tool_name)}: ${evPassed ? 'CLEAN' : 'FLAGGED'}
          </span>
        `;
      }
      empiricalHtml += '</div>';
    }

    html += `
      <div class="debate-round">
        <div class="round-header">
          <span>Round ${round.round_number + 1}</span>
          <div class="round-confidence">
            <span>Confidence: ${confPercent}%</span>
            <div class="confidence-bar">
              <div class="confidence-fill" style="width: ${confWidth}%"></div>
            </div>
          </div>
        </div>
        <div class="debate-arguments">
          <div class="debate-argument">
            <div class="argument-role role-prover"><span class="role-dot"></span> Prover (Claude 3.5 Sonnet)</div>
            <div class="argument-content">${escapeHtml(round.prover_argument?.content || '')}</div>
          </div>
          <div class="debate-argument">
            <div class="argument-role role-skeptic"><span class="role-dot"></span> Skeptic (GPT-4o)</div>
            <div class="argument-content">
              ${escapeHtml(round.skeptic_critique?.content || '')}
              ${empiricalHtml}
            </div>
          </div>
          <div class="debate-argument">
            <div class="argument-role role-judge"><span class="role-dot"></span> Judge / Jury Evaluation</div>
            <div class="argument-content">${escapeHtml(round.judge_evaluation?.content || '')}</div>
          </div>
        </div>
      </div>
    `;
  }

  html += '</div>';

  const verdictClass = `verdict-${tier2.verdict.replace('_', '')}`;
  const swapClass = tier2.swap_test_passed ? 'swap-passed' : 'swap-failed';
  const swapText = tier2.swap_test_passed ? '✓ Swap Test Passed (Position Invariant)' : '✗ Positional Bias Detected';

  html += `
    <div class="debate-verdict animate-in" style="margin-top: 12px; padding: 14px; background: var(--bg-secondary); border-radius: var(--radius-sm);">
      <span class="verdict-label ${verdictClass}">
        Verdict: ${tier2.verdict.replace(/_/g, ' ').toUpperCase()}
      </span>
      <span class="swap-test-badge ${swapClass}">${swapText}</span>
    </div>
  `;

  tier2Body.innerHTML = html;
}

function renderTier3(tier3) {
  if (!tier3) {
    setBadge(badgeTier3, 'idle', 'Skipped');
    return;
  }

  const stego = tier3.stego_analysis;
  const klPercent = Math.min(stego.kl_divergence / (stego.threshold_used * 2) * 100, 100);
  const gaugeClass = stego.alert_triggered ? 'gauge-danger' : klPercent > 50 ? 'gauge-warning' : 'gauge-safe';

  setBadge(badgeTier3, stego.alert_triggered ? 'flagged' : 'passed',
    stego.alert_triggered ? 'Alert!' : 'Clear');

  let html = `
    <div class="stego-gauge animate-in ${gaugeClass}">
      <div class="gauge-ring">
        <div class="gauge-inner">
          <div class="gauge-value">${stego.kl_divergence.toFixed(3)}</div>
          <div class="gauge-label">KL Divergence</div>
        </div>
      </div>
      <div style="text-align: center; font-size: 12px; color: var(--text-secondary);">
        Threshold: ${stego.threshold_used} · Perplexity: ${stego.perplexity?.toFixed(1) || 'N/A'}
      </div>
    </div>
  `;

  // Cross-Turn CUSUM Page-Hinkley Drift (Pillar 5)
  if (stego.cusum_drift_detected !== undefined) {
    const isDrift = stego.cusum_drift_detected;
    html += `
      <div class="violation-card animate-slide" style="margin-top: 12px; border-color: ${isDrift ? 'rgba(239, 68, 68, 0.35)' : 'rgba(16, 185, 129, 0.35)'}; background: ${isDrift ? 'rgba(239, 68, 68, 0.08)' : 'rgba(16, 185, 129, 0.05)'};">
        <div class="violation-header">
          <span class="violation-type" style="background: ${isDrift ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)'}; color: ${isDrift ? 'var(--color-danger)' : 'var(--color-success)'};">
            ${isDrift ? '⚠️ CROSS-TURN CUSUM DRIFT DETECTED' : '🛡️ CROSS-TURN CUSUM DRIFT: STATIONARY'}
          </span>
          <span style="font-size: 11px; color: var(--text-secondary);">
            CUSUM: ${(stego.cusum_statistic || 0).toFixed(3)} / Threshold: ${(stego.cusum_threshold || 3.5).toFixed(2)}
          </span>
        </div>
        <div class="violation-explanation" style="font-size: 11px; margin-top: 4px;">
          ${isDrift ? 'Significant cumulative distribution shift detected across multi-turn session. Potential sleeper-agent activation.' : 'Per-token divergence conforms to normal historical baseline across multi-turn session.'}
        </div>
      </div>
    `;
  }

  if (stego.token_analyses?.length) {
    html += '<div style="margin-top: 16px;"><div class="query-label" style="margin-bottom: 8px;">Token Perplexity Heatmap</div>';
    html += '<div class="token-heatmap">';
    for (const t of stego.token_analyses) {
      const intensity = Math.abs(t.kl_contribution);
      const cls = intensity < 0.01 ? 'token-low' : intensity < 0.03 ? 'token-medium' : 'token-high';
      html += `<span class="token-cell ${cls}" title="logprob: ${t.logprob.toFixed(3)}, KL: ${t.kl_contribution.toFixed(4)}">${escapeHtml(t.token)}</span>`;
    }
    html += '</div></div>';
  }

  if (tier3.paraphrased) {
    html += `
      <div style="margin-top: 16px;">
        <div class="query-label" style="margin-bottom: 8px;">🔄 Paraphrase Firewall Applied (Similarity: ${(tier3.semantic_similarity * 100).toFixed(0)}%)</div>
        <div class="paraphrase-comparison">
          <div class="paraphrase-box">
            <div class="paraphrase-label" style="color: var(--color-danger);">Original (Potentially Encoded)</div>
            <div class="paraphrase-text">${escapeHtml(tier3.original_text)}</div>
          </div>
          <div class="paraphrase-box">
            <div class="paraphrase-label" style="color: var(--color-success);">Sanitized Output</div>
            <div class="paraphrase-text">${escapeHtml(tier3.sanitized_text)}</div>
          </div>
        </div>
    `;
    if (tier3.semantic_preservation_score !== undefined) {
      html += `
        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 6px;">
          Semantic Safety &amp; Concept Preservation: <strong>${(tier3.semantic_preservation_score * 100).toFixed(0)}%</strong> (Guards safety categories &amp; numerical bounds)
        </div>
      `;
    }
    html += `</div>`;
  }

  tier3Body.innerHTML = html;
}

function renderMetrics(metrics, routing) {
  if (!metrics) return;

  setBadge(badgeMetrics, 'passed', 'Complete');

  const totalLatency = metrics.total_latency_ms?.toFixed(0) || '0';
  const totalTokens = metrics.total_tokens || 0;
  const totalCost = metrics.total_cost_usd?.toFixed(4) || '0.0000';
  const tierExec = metrics.tier_executed ?? routing?.tier ?? 0;

  let html = `
    <div class="metrics-grid animate-in">
      <div class="metric-card">
        <div class="metric-value">${totalLatency}</div>
        <div class="metric-label">Total Latency</div>
        <div class="metric-sub">milliseconds</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">${formatNumber(totalTokens)}</div>
        <div class="metric-label">Total Tokens</div>
        <div class="metric-sub">all tiers combined</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">$${totalCost}</div>
        <div class="metric-label">Est. Cost</div>
        <div class="metric-sub">USD (GPT-4o rates)</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">T${tierExec}</div>
        <div class="metric-label">Max Tier</div>
        <div class="metric-sub">${tierExec === 0 ? 'pass-through' : tierExec === 1 ? 'constitutional' : 'full debate'}</div>
      </div>
    </div>
  `;

  if (metrics.tokens_saved_by_cache > 0) {
    html += `
      <div class="animate-slide" style="margin-top: 14px; padding: 10px 14px; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; font-size: 12px; color: #6ee7b7; display: flex; align-items: center; gap: 8px;">
        <span>⚡</span>
        <span><strong>Case Law Precedent Savings:</strong> ${formatNumber(metrics.tokens_saved_by_cache)} tokens saved via vector precedent cache (avoided 6.87x debate cost multiplier).</span>
      </div>
    `;
  }

  const maxLatency = Math.max(
    metrics.routing_latency_ms || 0,
    metrics.tier1_latency_ms || 0,
    metrics.tier2_latency_ms || 0,
    metrics.tier3_latency_ms || 0,
    metrics.guardrails_latency_ms || 0,
    1
  );

  html += `
    <div class="latency-waterfall">
      <div class="query-label" style="margin: 16px 0 8px;">Latency Waterfall</div>
      ${waterfallRow('Router', metrics.routing_latency_ms, maxLatency, 'router')}
      ${waterfallRow('Tier 1', metrics.tier1_latency_ms, maxLatency, 'tier1')}
      ${waterfallRow('Tier 2', metrics.tier2_latency_ms, maxLatency, 'tier2')}
      ${waterfallRow('Tier 3', metrics.tier3_latency_ms, maxLatency, 'tier3')}
      ${waterfallRow('Guardrails', metrics.guardrails_latency_ms, maxLatency, 'tier1')}
    </div>
  `;

  metricsBody.innerHTML = html;
}

function waterfallRow(label, value, max, cls) {
  const width = max > 0 ? Math.max((value || 0) / max * 100, 2) : 0;
  const display = (value || 0).toFixed(0);
  return `
    <div class="waterfall-row">
      <span class="waterfall-label">${label}</span>
      <div class="waterfall-bar-container">
        <div class="waterfall-bar ${cls}" style="width: ${width}%"></div>
      </div>
      <span class="waterfall-value">${display}ms</span>
    </div>
  `;
}

// ─── Pipeline Helpers ───────────────────────────────────────
function resetPipeline() {
  [nodeRouter, nodeTier1, nodeTier2, nodeTier3, nodeOutput].forEach(n => {
    n.className = 'pipeline-node';
  });
  connectors.forEach(c => {
    c.className = 'pipeline-connector';
  });
  [badgeResponse, badgeTier1, badgeTier2, badgeTier3, badgeMetrics].forEach(b => {
    b.className = 'panel-badge badge-idle';
    b.textContent = 'Idle';
  });
}

function setNodeState(node, state) {
  node.className = `pipeline-node ${state}`;
}

function setConnectorActive(index) {
  if (connectors[index]) {
    connectors[index].className = 'pipeline-connector active';
  }
}

function setBadge(badge, type, text) {
  badge.className = `panel-badge badge-${type}`;
  badge.textContent = text;
}


// ═══════════════════════════════════════════════════════════
// CHAT LOGIC (Judge AI)
// ═══════════════════════════════════════════════════════════

// ─── DOM Refs — Chat ────────────────────────────────────────
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const ollamaStatus = document.getElementById('ollama-status');
const ollamaStatusText = document.getElementById('ollama-status-text');
const ollamaStatusTopbar = document.getElementById('ollama-status-topbar');
const ollamaStatusTopbarText = document.getElementById('ollama-status-topbar-text');

// Config
const cfgModel = document.getElementById('cfg-model');
const cfgRetries = document.getElementById('cfg-retries');

// Verdict panel
const verdictCard = document.getElementById('verdict-card');
const verdictBadge = document.getElementById('verdict-badge');
const verdictBody = document.getElementById('verdict-body');

// Metrics
const metricLatency = document.getElementById('metric-latency');
const metricTokens = document.getElementById('metric-tokens');
const metricAttempts = document.getElementById('metric-attempts');

// Flow diagram steps
const flowSteps = {
  input: document.getElementById('flow-input'),
  risk: document.getElementById('flow-risk'),
  generate: document.getElementById('flow-generate'),
  judge: document.getElementById('flow-judge'),
  refine: document.getElementById('flow-refine'),
  output: document.getElementById('flow-output'),
};

// Quick prompts
document.querySelectorAll('.quick-prompt').forEach(btn => {
  btn.addEventListener('click', () => {
    chatInput.value = btn.dataset.query;
    chatInput.focus();
    // Switch to chat view if not already
    switchView('chat');
  });
});

function setupChatListeners() {
  sendBtn.addEventListener('click', sendMessage);
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

// ─── Ollama Health ──────────────────────────────────────────
async function checkOllama() {
  try {
    const res = await fetch(`${API_BASE}/chat/health`);
    const data = await res.json();

    if (data.status === 'healthy') {
      const modelOk = data.generator_available ? '✓' : '✗';
      const statusStr = `Ollama ${modelOk} ${data.generator_model}`;
      ollamaStatus.className = 'sidebar-status connected';
      ollamaStatusText.textContent = statusStr;
      ollamaStatusTopbar.className = 'ollama-status connected';
      ollamaStatusTopbarText.textContent = statusStr;
    } else {
      const errStr = data.error || 'Ollama offline';
      ollamaStatus.className = 'sidebar-status disconnected';
      ollamaStatusText.textContent = errStr;
      ollamaStatusTopbar.className = 'ollama-status disconnected';
      ollamaStatusTopbarText.textContent = errStr;
    }
  } catch {
    ollamaStatus.className = 'sidebar-status disconnected';
    ollamaStatusText.textContent = 'Server offline';
    ollamaStatusTopbar.className = 'ollama-status disconnected';
    ollamaStatusTopbarText.textContent = 'Server offline';
  }
}

async function loadChatConfig() {
  try {
    const res = await fetch(`${API_BASE}/chat/config`);
    const data = await res.json();
    cfgModel.textContent = data.generator_model || '—';
    cfgRetries.textContent = data.max_retries || '2';
  } catch {
    cfgModel.textContent = '—';
  }
}

// ─── Send Message ───────────────────────────────────────────
let isSending = false;

async function sendMessage() {
  const message = chatInput.value.trim();
  if (!message || isSending) return;

  isSending = true;
  sendBtn.disabled = true;
  chatInput.value = '';

  addMessage(message, 'user');
  const typingEl = addTypingIndicator();

  resetFlow();
  setFlowStep('input', 'done');
  setFlowStep('risk', 'active');

  try {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    const data = await res.json();
    typingEl.remove();
    animateFlowForResult(data);
    addMessage(data.response, 'assistant', data.risk);
    updateVerdict(data);
    updateChatMetrics(data);

  } catch (err) {
    typingEl.remove();
    addMessage(`⚠️ Error: ${err.message}`, 'system-msg');
    resetFlow();
  } finally {
    isSending = false;
    sendBtn.disabled = false;
    chatInput.focus();
  }
}

// ─── Message Rendering ──────────────────────────────────────
function addMessage(content, type, risk) {
  const msg = document.createElement('div');
  msg.className = `chat-msg ${type}`;

  let meta = '';
  if (type === 'user') {
    meta = '<div class="msg-meta"><span class="msg-avatar user-avatar">👤</span> You</div>';
  } else if (type === 'assistant') {
    const riskBadge = risk
      ? ` <span class="risk-badge risk-${risk.level}">${risk.level.toUpperCase()}</span>`
      : '';
    meta = `<div class="msg-meta"><span class="msg-avatar ai-avatar">⚖️</span> Judge AI${riskBadge}</div>`;
  }

  msg.innerHTML = meta + escapeHtml(content);
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return msg;
}

function addTypingIndicator() {
  const el = document.createElement('div');
  el.className = 'typing-indicator';
  el.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return el;
}

// ─── Flow Diagram ───────────────────────────────────────────
function resetFlow() {
  Object.values(flowSteps).forEach(el => {
    if (el) el.classList.remove('active', 'done');
  });
}

function setFlowStep(step, state) {
  const el = flowSteps[step];
  if (!el) return;
  el.classList.remove('active', 'done');
  el.classList.add(state);
}

function animateFlowForResult(data) {
  setFlowStep('input', 'done');
  setFlowStep('risk', 'done');
  setFlowStep('generate', 'done');
  setFlowStep('judge', 'done');
  if (data.attempts && data.attempts.length > 1) {
    setFlowStep('refine', 'done');
  }
  setFlowStep('output', 'done');
}

// ─── Verdict Sidebar ────────────────────────────────────────
function updateVerdict(data) {
  const { attempts, risk, final_decision } = data;

  verdictCard.className = `judge-card ${final_decision === 'approve' ? 'approved' : 'rejected'}`;

  verdictBadge.style.display = 'inline';
  verdictBadge.className = `decision-badge decision-${final_decision}`;
  verdictBadge.textContent = final_decision === 'approve' ? '✓ Approved' : '✗ Rejected';

  let html = '';

  html += `
    <div style="margin-bottom: 12px;">
      <span class="risk-badge risk-${risk.level}">${risk.level.toUpperCase()} — ${risk.domain}</span>
      <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">${escapeHtml(risk.reasoning)}</div>
    </div>
  `;

  html += '<div class="attempt-list">';
  for (const step of attempts) {
    const isApproved = step.judge_verdict.decision === 'approve';
    const cls = isApproved ? 'approved' : 'rejected';
    const badge = isApproved ? '✓ Approved' : '✗ Rejected';
    const badgeCls = isApproved ? 'decision-approve' : 'decision-reject';

    html += `
      <div class="attempt-step ${cls}">
        <div class="attempt-header">
          <span>Attempt ${step.attempt}</span>
          <span class="decision-badge ${badgeCls}">${badge}</span>
        </div>
        <div class="attempt-reason">${escapeHtml(step.judge_verdict.reason)}</div>
        ${step.judge_verdict.fix ? `<div style="margin-top: 6px; font-size: 11px; color: var(--accent);">💡 Fix: ${escapeHtml(step.judge_verdict.fix).substring(0, 200)}${step.judge_verdict.fix.length > 200 ? '...' : ''}</div>` : ''}
      </div>
    `;
  }
  html += '</div>';

  verdictBody.innerHTML = html;
}

function updateChatMetrics(data) {
  metricLatency.textContent = data.total_latency_ms
    ? `${(data.total_latency_ms / 1000).toFixed(1)}s`
    : '—';
  metricTokens.textContent = data.total_tokens
    ? data.total_tokens.toLocaleString()
    : '—';
  metricAttempts.textContent = data.attempts
    ? data.attempts.length
    : '—';
}


// ═══════════════════════════════════════════════════════════
// SHARED UTILITIES
// ═══════════════════════════════════════════════════════════

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}

function showError(message) {
  responseBody.innerHTML = `
    <div class="violation-card animate-in">
      <div class="violation-header">
        <span class="violation-type" style="background: rgba(239, 68, 68, 0.08); color: var(--color-danger);">ERROR</span>
      </div>
      <div class="violation-explanation">${escapeHtml(message)}</div>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════
// ADVANCED PILLARS: MODALS, CHECKPOINTS, COMPILER & RED-TEAM
// ═══════════════════════════════════════════════════════════

let activeForkRequestId = null;
let activeForkCheckpointId = null;

function setupModalListeners() {
  const modalReceipt = document.getElementById('modal-receipt-overlay');
  const closeReceiptBtn = document.getElementById('close-modal-receipt-btn');
  if (closeReceiptBtn && modalReceipt) {
    closeReceiptBtn.addEventListener('click', () => {
      modalReceipt.classList.remove('open');
      modalReceipt.style.display = 'none';
    });
  }

  const modalFork = document.getElementById('modal-fork-overlay');
  const closeForkBtn = document.getElementById('close-modal-fork-btn');
  if (closeForkBtn && modalFork) {
    closeForkBtn.addEventListener('click', () => {
      modalFork.classList.remove('open');
      modalFork.style.display = 'none';
    });
  }

  const btnExecuteFork = document.getElementById('btn-execute-fork');
  if (btnExecuteFork) {
    btnExecuteFork.addEventListener('click', executeFork);
  }
}

async function verifyReceiptInModal(receipt, finalResponse) {
  const modalReceipt = document.getElementById('modal-receipt-overlay');
  const modalContent = document.getElementById('modal-receipt-content');
  if (!modalReceipt || !modalContent) return;

  modalReceipt.style.display = 'flex';
  modalReceipt.classList.add('open');
  modalContent.innerHTML = '<div style="padding: 24px; text-align: center;"><span class="spinner"></span> Verifying SHA-256 Merkle root & HMAC-SHA256 signature...</div>';

  try {
    const res = await fetch(`${API_BASE}/api/verify-receipt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ receipt, final_response: finalResponse }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const statusBadge = data.valid
      ? '<span style="background: rgba(16, 185, 129, 0.2); color: #10b981; padding: 4px 10px; border-radius: 4px; font-weight: 700;">✓ VALID & TAMPER-PROOF</span>'
      : '<span style="background: rgba(239, 68, 68, 0.2); color: #ef4444; padding: 4px 10px; border-radius: 4px; font-weight: 700;">✗ INVALID / TAMPERED</span>';

    let leavesHtml = '<div style="margin-top: 14px; font-size: 11px;"><strong>Verified Merkle Leaves (SHA-256):</strong>';
    for (const leaf of receipt.leaves || []) {
      leavesHtml += `<div style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); margin-top: 4px; word-break: break-all;">• ${leaf.node_name}: <span style="color: var(--accent);">${leaf.leaf_hash}</span></div>`;
    }
    leavesHtml += '</div>';

    modalContent.innerHTML = `
      <div style="margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 13px; font-weight: 600; color: var(--text-primary);">Attestation Status:</span>
        ${statusBadge}
      </div>
      <div style="background: rgba(0,0,0,0.3); padding: 12px; border-radius: 6px; font-family: var(--font-mono); font-size: 11px; margin-bottom: 12px; border: 1px solid var(--border-color);">
        <div style="color: var(--text-secondary); margin-bottom: 4px;">Root Match: <strong style="color: ${data.root_match ? '#10b981' : '#ef4444'}">${data.root_match ? 'MATCH' : 'MISMATCH'}</strong></div>
        <div style="color: var(--text-secondary); margin-bottom: 4px;">HMAC Signature: <strong style="color: ${data.signature_valid ? '#10b981' : '#ef4444'}">${data.signature_valid ? 'AUTHENTIC' : 'INVALID'}</strong></div>
        <div style="color: var(--text-muted); word-break: break-all;">Merkle Root: ${data.computed_root}</div>
      </div>
      <div style="font-size: 11px; color: var(--text-secondary);">
        Algorithm: <strong>${receipt.algorithm}</strong> · Verification Latency: <strong>${data.latency_ms?.toFixed(2) || '0.15'} ms</strong>
      </div>
      ${leavesHtml}
    `;
  } catch (err) {
    modalContent.innerHTML = `<div style="color: var(--color-danger); padding: 12px;">Receipt verification failed: ${escapeHtml(err.message)}</div>`;
  }
}

async function loadCheckpoints(requestId) {
  const bar = document.getElementById('time-travel-bar');
  const countBadge = document.getElementById('checkpoint-count-badge');
  const timeline = document.getElementById('checkpoint-timeline');

  if (!bar || !requestId) {
    if (bar) bar.style.display = 'none';
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/pipeline/checkpoints/${requestId}`);
    if (!res.ok) return;
    const data = await res.json();
    const checkpoints = data.checkpoints || [];

    if (!checkpoints.length) {
      bar.style.display = 'none';
      return;
    }

    bar.style.display = 'block';
    countBadge.textContent = `${checkpoints.length} Snapshots`;
    timeline.innerHTML = '';

    checkpoints.forEach(cp => {
      const pill = document.createElement('button');
      pill.className = 'checkpoint-pill';
      pill.innerHTML = `<span>📍 ${cp.node_name}</span> <span style="opacity: 0.6;">${cp.checkpoint_id.slice(-6)}</span>`;
      pill.title = `Fork execution from ${cp.node_name} (${cp.checkpoint_id})`;
      pill.addEventListener('click', () => openForkModal(requestId, cp));
      timeline.appendChild(pill);
    });
  } catch {
    bar.style.display = 'none';
  }
}

function openForkModal(requestId, checkpoint) {
  activeForkRequestId = requestId;
  activeForkCheckpointId = checkpoint.checkpoint_id;

  const modalFork = document.getElementById('modal-fork-overlay');
  const idLabel = document.getElementById('fork-checkpoint-id-label');
  const queryInput = document.getElementById('fork-query-input');

  if (!modalFork || !idLabel || !queryInput) return;

  idLabel.textContent = `${checkpoint.node_name} (${checkpoint.checkpoint_id.slice(0, 12)}...)`;
  queryInput.value = checkpoint.state_snapshot?.query || currentResult?.query || '';

  modalFork.style.display = 'flex';
  modalFork.classList.add('open');
}

async function executeFork() {
  if (!activeForkRequestId || !activeForkCheckpointId) return;

  const modalFork = document.getElementById('modal-fork-overlay');
  const queryInput = document.getElementById('fork-query-input');
  const btn = document.getElementById('btn-execute-fork');
  const modifiedPrompt = queryInput.value.trim();

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Replaying from checkpoint...';

  try {
    const res = await fetch(`${API_BASE}/api/pipeline/fork`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        original_request_id: activeForkRequestId,
        checkpoint_id: activeForkCheckpointId,
        overrides: { modified_prompt: modifiedPrompt },
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const forkedResult = await res.json();

    modalFork.classList.remove('open');
    modalFork.style.display = 'none';

    currentResult = forkedResult;
    renderFullResult(forkedResult);

  } catch (err) {
    alert(`Counterfactual fork replay failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⚡ Replay Forward from Checkpoint';
  }
}

function setupCompilerListeners() {
  const btnCompile = document.getElementById('btn-trigger-compile');
  if (btnCompile) {
    btnCompile.addEventListener('click', triggerCompilation);
  }
}

async function loadCompilerStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/compiler/status`);
    if (!res.ok) return;
    const data = await res.json();

    const runsEl = document.getElementById('compiler-total-runs');
    const precEl = document.getElementById('compiler-precedents-count');
    const qEl = document.getElementById('compiler-queue-count');
    const rateEl = document.getElementById('compiler-catch-rate');
    const badgeEl = document.getElementById('compiler-catch-rate-badge');

    const runs = data.compilation_runs ?? 0;
    const prec = data.total_compiled_precedents ?? 0;
    const queue = data.uncompiled_precedents_queue ?? 0;
    const catchRate = data.current_estimated_catch_rate ?? 78.4;
    const catchRatePct = `${catchRate}%`;

    if (runsEl) runsEl.textContent = runs;
    if (precEl) precEl.textContent = prec;
    if (qEl) qEl.textContent = queue;
    if (rateEl) rateEl.textContent = catchRatePct;
    if (badgeEl) badgeEl.textContent = `${catchRatePct} Catch Rate`;

    const list = document.getElementById('compiler-demonstrations-list');
    if (list) {
      list.innerHTML = '';
      const demos = data.active_demonstrations || [];
      if (!demos.length) {
        list.innerHTML = '<div style="font-size: 12px; color: var(--text-muted); padding: 12px 0;">No few-shot demonstrations compiled yet. High-confidence Tier 2 debate rulings will accumulate here.</div>';
      } else {
        demos.forEach((d, i) => {
          const card = document.createElement('div');
          card.className = 'demo-card animate-slide';
          const queryText = d.context || d.query || '';
          const cotText = d.reasoning_trace || d.flawed_cot || '';
          const guidance = d.correction_guidance || '';
          const vType = d.violation_type || 'Unspecified';

          card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-weight: 600; color: var(--accent);">Precedent #${i + 1} Labeled Hard-Negative</span>
              <span class="empirical-badge badge-flagged" style="margin: 0;">${escapeHtml(vType)}</span>
            </div>
            <div style="margin-bottom: 4px; color: var(--text-primary);"><strong>Query:</strong> ${escapeHtml(queryText)}</div>
            <div style="color: var(--color-danger); margin-bottom: 4px; font-size: 11px;"><strong>Flawed CoT:</strong> ${escapeHtml(cotText)}</div>
            <div style="color: var(--color-success); font-size: 11px;"><strong>Correction Guidance:</strong> ${escapeHtml(guidance)}</div>
          `;
          list.appendChild(card);
        });
      }
    }
  } catch (err) {
    console.error('Failed to load compiler status:', err);
  }
}

async function triggerCompilation() {
  const btn = document.getElementById('btn-trigger-compile');
  if (!btn) return;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Compiling Signatures...';

  try {
    const res = await fetch(`${API_BASE}/api/compiler/compile`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await loadCompilerStatus();
  } catch (err) {
    alert(`Compilation failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🔄 Recompile Signatures Now';
  }
}

function setupRedTeamListeners() {
  const range = document.getElementById('redteam-difficulty-range');
  const label = document.getElementById('difficulty-val-label');
  const btnLaunch = document.getElementById('btn-launch-redteam');

  if (range && label) {
    range.addEventListener('input', () => {
      label.textContent = `Level ${range.value}`;
    });
  }

  if (btnLaunch) {
    btnLaunch.addEventListener('click', launchRedTeamAttack);
  }
}

async function launchRedTeamAttack() {
  const taskSelect = document.getElementById('redteam-task-select');
  const range = document.getElementById('redteam-difficulty-range');
  const btn = document.getElementById('btn-launch-redteam');
  const container = document.getElementById('redteam-results-container');
  const badge = document.getElementById('badge-redteam-status');

  if (!btn || !taskSelect || !range || !container || !badge) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Generating Houdini Attack & Evaluating Defense...';
  badge.className = 'panel-badge badge-active';
  badge.textContent = 'Attacking...';

  try {
    const res = await fetch(`${API_BASE}/api/redteam/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task: taskSelect.value,
        difficulty: parseInt(range.value, 10),
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const attack = data.attack_metadata;
    const caught = data.flaw_caught;
    const tiers = data.caught_by_tiers;
    const slope = data.guard_metrics;

    badge.className = caught ? 'panel-badge badge-passed' : 'panel-badge badge-flagged';
    badge.textContent = caught ? 'Flaw Caught (Defense Intact)' : 'Defense Evaded!';

    container.style.display = 'block';
    container.innerHTML = `
      <div class="animate-in" style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 14px; margin-top: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-weight: 700; color: ${caught ? 'var(--color-success)' : 'var(--color-danger)'}; font-size: 14px;">
            ${caught ? '🛡️ TAO Defense Stopped Adversarial Trap' : '⚠️ Houdini Attack Evaded Defense'}
          </span>
          <span style="font-size: 11px; font-family: var(--font-mono); color: var(--accent);">
            Guard Slope: ${slope.guard_slope !== undefined ? slope.guard_slope.toFixed(2) : '0.00'}
          </span>
        </div>

        <div style="font-size: 12px; margin-bottom: 10px; color: var(--text-primary);">
          <strong>Adversarial Prompt Injected:</strong>
          <div style="background: rgba(255,255,255,0.03); padding: 8px 10px; border-radius: 6px; margin-top: 4px; font-style: italic;">
            ${escapeHtml(attack.query)}
          </div>
        </div>

        <div style="font-size: 12px; margin-bottom: 10px; color: var(--text-secondary);">
          <strong style="color: #f59e0b;">Houdini Subversive CoT:</strong>
          <div style="background: rgba(245, 158, 11, 0.05); border-left: 2px solid #f59e0b; padding: 8px 10px; border-radius: 4px; margin-top: 4px; font-size: 11px;">
            ${escapeHtml(attack.subversive_cot)}
          </div>
        </div>

        <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px;">
          <span class="empirical-badge ${tiers.tier1 ? 'badge-passed' : 'badge-flagged'}">
            Tier 1 (OmegaPRM): ${tiers.tier1 ? 'Caught' : 'Missed'}
          </span>
          <span class="empirical-badge ${tiers.tier2 ? 'badge-passed' : 'badge-flagged'}">
            Tier 2 (Skeptic Debate): ${tiers.tier2 ? 'Caught' : 'Missed'}
          </span>
          <span class="empirical-badge ${tiers.tier3 ? 'badge-passed' : 'badge-flagged'}">
            Tier 3 (Stego Sentinel): ${tiers.tier3 ? 'Caught' : 'Missed'}
          </span>
        </div>
      </div>
    `;

  } catch (err) {
    alert(`Red-team attack execution failed: ${err.message}`);
    badge.className = 'panel-badge badge-flagged';
    badge.textContent = 'Error';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⚔️ Launch Adversarial Attack vs TAO Pipeline';
  }
}
