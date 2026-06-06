/* ========================================
   Elder Scam Shield — Interactive Demo
   ======================================== */

(function () {
  'use strict';

  // ---- State ----
  var currentScene = 1;
  var currentDay = 1;
  var visitedScenes = new Set([1]);
  var visitedDays = new Set([1]);

  // ---- Day data for sender profile ----
  var dayProfileData = {
    1: {
      messages: '1',
      locations: '&mdash;',
      contactMatch: '&mdash;',
      contradictions: '0',
      financial: '&mdash;',
      riskVal: '0.08',
      riskWidth: '8%',
      riskClass: '',
    },
    3: {
      messages: '3',
      locations: '<span class="fact-tag" style="font-size:0.78rem">Osaka (大阪) &mdash; Day 3</span>',
      contactMatch: '<span style="color:#f59e0b;font-weight:600">Checking...</span>',
      contradictions: '0',
      financial: '&mdash;',
      riskVal: '0.12',
      riskWidth: '12%',
      riskClass: '',
    },
    5: {
      messages: '5',
      locations:
        '<span class="fact-tag" style="font-size:0.78rem">Osaka (大阪) &mdash; Day 3</span>' +
        '<br><span class="fact-tag" style="font-size:0.78rem;background:#fef2f2;color:#dc2626">Tokyo hospital (東京の病院) &mdash; Day 5</span>',
      contactMatch: '<span style="color:#dc2626;font-weight:600">NO MATCH &mdash; grandson is Takeshi (武)</span>',
      contradictions: '<span class="pf-contradiction" style="color:#dc2626;font-weight:700">2</span>',
      financial: '&mdash;',
      riskVal: '0.72',
      riskWidth: '72%',
      riskClass: 'risk-med',
    },
    7: {
      messages: '7',
      locations:
        '<span class="fact-tag" style="font-size:0.78rem">Osaka (大阪) &mdash; Day 3</span>' +
        '<br><span class="fact-tag" style="font-size:0.78rem;background:#fef2f2;color:#dc2626">Tokyo hospital (東京の病院) &mdash; Day 5</span>',
      contactMatch: '<span style="color:#dc2626;font-weight:600">NO MATCH &mdash; grandson is Takeshi (武)</span>',
      contradictions: '<span class="pf-contradiction" style="color:#dc2626;font-weight:700">2</span>',
      financial: '<span class="pf-financial-danger" style="color:#dc2626;font-weight:700">&yen;500,000 &mdash; Day 7, urgency: HIGH</span>',
      riskVal: '0.94',
      riskWidth: '94%',
      riskClass: 'risk-high',
    },
  };

  // ---- Day data for reasoning trace ----
  var dayTraceData = {
    1: [
      {
        agent: 'Inbound Classifier',
        detail: 'Classification: <strong>safe</strong>. No known scam patterns matched. Extracted: name=Kenji, relationship=grandson.',
        cls: '',
      },
    ],
    3: [
      {
        agent: 'Inbound Classifier',
        detail: 'Classification: <strong>safe</strong>. Extracted: location=Osaka, context=new job. No urgency or financial signals.',
        cls: '',
      },
      {
        agent: 'Behavioral Analyzer',
        detail: 'Sender profile updated. 3 messages over 3 days. Building location history. Contact verification: pending.',
        cls: '',
      },
    ],
    5: [
      {
        agent: 'Inbound Classifier',
        detail: 'Classification: <strong>safe</strong> (single-message analysis). Extracted: location=Tokyo hospital, context=accident.',
        cls: '',
      },
      {
        agent: 'Behavioral Analyzer',
        detail:
          '<strong>LOCATION CONTRADICTION DETECTED</strong>: Claimed Osaka on Day 3, now claims Tokyo hospital on Day 5. Geographic shift: 500km in 48h without travel context.',
        cls: 'trace-warn',
      },
      {
        agent: 'Behavioral Analyzer',
        detail:
          '<strong>CONTACT MISMATCH</strong>: Sender claims to be grandson "Kenji" (健二). User contact book lists grandson as "Takeshi" (武). No contact named Kenji found.',
        cls: 'trace-warn',
      },
      {
        agent: 'Behavioral Analyzer',
        detail: 'Risk score elevated: 0.12 &rarr; <strong>0.72</strong>. Two independent contradiction signals. Monitoring escalated.',
        cls: 'trace-warn',
      },
    ],
    7: [
      {
        agent: 'Inbound Classifier',
        detail:
          'Classification: <strong>suspicious</strong>. Signals: financial request (&yen;500,000), urgency phrase ("今日中に" = "within today"), payment solicitation.',
        cls: 'trace-danger',
      },
      {
        agent: 'Behavioral Analyzer',
        detail:
          '<strong>COMPOUND RISK ASSESSMENT</strong>: Money request (&yen;500,000) + urgency ("today") + 2 prior contradictions + confirmed contact mismatch + 7-day trust-building pattern.',
        cls: 'trace-danger',
      },
      {
        agent: 'Behavioral Analyzer',
        detail:
          'Pattern match: <strong>ore-ore sagi (オレオレ詐欺) / grandchild impersonation</strong>. Classic 7-day trust escalation with financial request on final day.',
        cls: 'trace-danger',
      },
      {
        agent: 'Behavioral Analyzer',
        detail: 'Risk score: 0.72 &rarr; <strong>0.94</strong>. Verdict: <strong>BLOCKED</strong>. Message quarantined, not delivered to user.',
        cls: 'trace-danger',
      },
    ],
  };

  // ---- DOM helpers ----
  function $(sel, ctx) {
    return (ctx || document).querySelector(sel);
  }
  function $$(sel, ctx) {
    return Array.from((ctx || document).querySelectorAll(sel));
  }

  // ---- Scene navigation ----
  function goToScene(n) {
    n = parseInt(n, 10);
    if (n < 1 || n > 4) return;

    // Hide current
    var cur = $('#scene-' + currentScene);
    if (cur) cur.classList.remove('scene-active');

    // Show target
    var next = $('#scene-' + n);
    if (next) next.classList.add('scene-active');

    currentScene = n;
    visitedScenes.add(n);
    updateNavDots();

    // Reset day when entering scene 2
    if (n === 2 && !visitedDays.has(1)) {
      goToDay(1);
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function updateNavDots() {
    $$('.nav-dot').forEach(function (dot) {
      var s = parseInt(dot.dataset.scene, 10);
      dot.classList.remove('active', 'visited');
      if (s === currentScene) {
        dot.classList.add('active');
      } else if (visitedScenes.has(s)) {
        dot.classList.add('visited');
      }
    });
  }

  // ---- Day navigation (Scene 2) ----
  function goToDay(d) {
    d = parseInt(d, 10);
    currentDay = d;
    visitedDays.add(d);

    // Update timeline buttons
    $$('.timeline-day').forEach(function (btn) {
      var bd = parseInt(btn.dataset.day, 10);
      btn.classList.remove('active', 'visited', 'warn-day', 'danger');
      if (bd === d) {
        if (d === 7) btn.classList.add('danger');
        else if (d === 5) btn.classList.add('warn-day');
        else btn.classList.add('active');
      } else if (visitedDays.has(bd)) {
        btn.classList.add('visited');
      }
    });

    // Show day panel
    $$('.day-panel').forEach(function (p) {
      p.classList.remove('day-panel-active');
    });
    var panel = $('#day-' + d);
    if (panel) panel.classList.add('day-panel-active');

    // Update sender profile
    updateProfile(d);

    // Update reasoning trace
    updateTrace(d);
  }

  function updateProfile(d) {
    var data = dayProfileData[d];
    if (!data) return;

    $('#pf-messages').textContent = data.messages;
    $('#pf-locations').innerHTML = data.locations;
    $('#pf-contact-match').innerHTML = data.contactMatch;
    $('#pf-contradictions').innerHTML = data.contradictions;
    $('#pf-financial').innerHTML = data.financial;
    $('#pf-risk-val').textContent = data.riskVal;

    var fill = $('#pf-risk-fill');
    fill.style.width = data.riskWidth;
    fill.className = 'mini-risk-fill';
    if (data.riskClass) fill.classList.add(data.riskClass);
  }

  function updateTrace(d) {
    var entries = dayTraceData[d];
    if (!entries) return;

    var container = $('#trace-content');
    container.innerHTML = '';

    entries.forEach(function (e) {
      var div = document.createElement('div');
      div.className = 'trace-entry' + (e.cls ? ' ' + e.cls : '');
      div.innerHTML =
        '<span class="trace-agent">' + e.agent + '</span>' +
        '<span class="trace-detail">' + e.detail + '</span>';
      container.appendChild(div);
    });

    // Auto-open trace on days 5 and 7
    var tracePanel = $('#trace-panel');
    if (d >= 5) {
      tracePanel.setAttribute('open', '');
    } else {
      tracePanel.removeAttribute('open');
    }
  }

  // ---- Event Binding ----
  function init() {
    // Nav dots
    $$('.nav-dot').forEach(function (dot) {
      dot.addEventListener('click', function () {
        goToScene(this.dataset.scene);
      });
    });

    // Scene nav buttons
    $$('[data-goto]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        goToScene(this.dataset.goto);
      });
    });

    // Timeline days
    $$('.timeline-day').forEach(function (btn) {
      btn.addEventListener('click', function () {
        goToDay(this.dataset.day);
      });
    });

    // Keyboard navigation
    document.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        if (currentScene === 2) {
          var days = [1, 3, 5, 7];
          var idx = days.indexOf(currentDay);
          if (idx < days.length - 1) {
            goToDay(days[idx + 1]);
            return;
          }
        }
        if (currentScene < 4) goToScene(currentScene + 1);
      }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (currentScene === 2) {
          var days2 = [1, 3, 5, 7];
          var idx2 = days2.indexOf(currentDay);
          if (idx2 > 0) {
            goToDay(days2[idx2 - 1]);
            return;
          }
        }
        if (currentScene > 1) goToScene(currentScene - 1);
      }
    });

    // Initialize first scene
    goToScene(1);
    goToDay(1);
  }

  // ---- Live Classify (Scene 5) ----
  function initLiveClassify() {
    var btn = document.getElementById('live-classify-btn');
    var msgInput = document.getElementById('live-message');
    var senderInput = document.getElementById('live-sender');
    var resultDiv = document.getElementById('live-result');
    var loadingDiv = document.getElementById('live-loading');
    var outputDiv = document.getElementById('live-output');
    var errorDiv = document.getElementById('live-error');
    var timerSpan = document.getElementById('live-timer');

    if (!btn) return;

    // Example buttons
    document.getElementById('live-example-scam').addEventListener('click', function () {
      senderInput.value = 'unknown_0x9f3a';
      msgInput.value = '重要なお知らせ：貴殿のインターネット利用料金に未払いが発生しております。本日中にお支払いいただけない場合、法的措置を取らせていただきます。至急、コンビニにて電子マネーでお支払いください。未払い額：89,000円。';
    });
    document.getElementById('live-example-safe').addEventListener('click', function () {
      senderInput.value = 'contact_yuki_grandson';
      msgInput.value = 'おばあちゃん、ゆきです！来週の土曜日、横浜から遊びに行くね。何か食べたいものある？お土産持っていくから楽しみにしてて！';
    });

    btn.addEventListener('click', function () {
      var message = msgInput.value.trim();
      var sender = senderInput.value.trim();
      if (!message) { msgInput.focus(); return; }

      resultDiv.style.display = 'block';
      loadingDiv.style.display = 'block';
      outputDiv.style.display = 'none';
      errorDiv.style.display = 'none';
      btn.disabled = true;
      btn.textContent = 'Classifying...';

      var startTime = Date.now();
      var timerInterval = setInterval(function () {
        timerSpan.textContent = ((Date.now() - startTime) / 1000).toFixed(1) + 's';
      }, 100);

      fetch('/api/classify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender: sender, content: message })
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          clearInterval(timerInterval);
          loadingDiv.style.display = 'none';
          btn.disabled = false;
          btn.innerHTML = 'Classify with Live Gemini &rarr;';

          if (data.result && data.result.classification) {
            outputDiv.style.display = 'block';
            var res = data.result;
            var cls = res.classification || 'unknown';

            var classBox = document.getElementById('live-class-box');
            var classLabel = document.getElementById('live-class-label');
            classLabel.textContent = cls.toUpperCase();
            classBox.style.background =
              cls === 'scam' ? 'var(--red-bg)' :
              cls === 'suspicious' ? 'var(--yellow-bg)' :
              cls === 'safe' ? 'var(--green-bg)' : 'var(--gray-50)';
            classLabel.style.color =
              cls === 'scam' ? 'var(--red)' :
              cls === 'suspicious' ? 'var(--yellow)' :
              cls === 'safe' ? 'var(--green)' : 'var(--navy)';

            document.getElementById('live-confidence').textContent =
              (res.confidence != null ? (res.confidence * 100).toFixed(0) + '%' : 'N/A');

            var sigDiv = document.getElementById('live-signals');
            sigDiv.innerHTML = '';
            var signals = res.detected_signals || [];
            if (signals.length === 0) {
              sigDiv.innerHTML = '<span style="color:#999;">None detected</span>';
            } else {
              signals.forEach(function (s) {
                var span = document.createElement('span');
                span.className = 'flag ' + (s.startsWith('PM-') ? 'flag-danger' : 'flag-warn');
                span.textContent = s;
                sigDiv.appendChild(span);
              });
            }

            var facts = res.extracted_facts || {};
            document.getElementById('live-facts').textContent = JSON.stringify(facts, null, 2);
            document.getElementById('live-reasoning').textContent = res.reasoning || '—';
          } else {
            errorDiv.style.display = 'block';
            errorDiv.textContent = 'Unexpected response: ' + JSON.stringify(data).substring(0, 300);
          }
        })
        .catch(function (err) {
          clearInterval(timerInterval);
          loadingDiv.style.display = 'none';
          errorDiv.style.display = 'block';
          errorDiv.textContent = 'Error: ' + err.message + '. Is the server running? (uvicorn app:app --port 8080)';
          btn.disabled = false;
          btn.innerHTML = 'Classify with Live Gemini &rarr;';
        });
    });
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { init(); initLiveClassify(); });
  } else {
    init();
    initLiveClassify();
  }
})();
