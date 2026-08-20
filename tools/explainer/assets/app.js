/* openCG architecture explainer.
 *
 * Vanilla JS on purpose: the output has to be one self-contained file that
 * works offline, off a file:// URL, and when emailed to someone. No CDN, no
 * framework, no build step.
 *
 * Every version snapshot is inlined by the generator, so switching versions
 * and diffing them are both local operations with no fetch.
 */
(function () {
  "use strict";

  var PAYLOAD = JSON.parse(document.getElementById("explainer-data").textContent);
  var VERSIONS = PAYLOAD.versions.slice().sort(function (a, b) { return a.seq - b.seq; });
  var LATEST = VERSIONS[VERSIONS.length - 1];

  var state = {
    version: LATEST,
    compare: null,     // set -> diff mode
    route: "overview",
    openSteps: {},
    openChanges: {},
    changeFilter: null,
    searchSel: 0,
    searchHits: []
  };

  var view = document.getElementById("view");
  var nav = document.getElementById("nav");

  /* ---------------- helpers ---------------- */

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Pillar prose arrives pre-rendered and pre-escaped from the Python side.
  function raw(s) { return s == null ? "" : String(s); }

  function stripTags(s) { return String(s == null ? "" : s).replace(/<[^>]*>/g, ""); }

  function data() { return state.version.data; }

  function pillars() { return data().pillars; }

  function pillarById(id) {
    var list = pillars();
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }

  function statusBadge(status) {
    var map = {
      shipped: ["shipped", "Shipped"],
      partial: ["partial", "Partial"],
      planned: ["planned", "Planned"],
      "in-flight": ["inflight", "In flight"],
      "not-started": ["notstarted", "Not started"]
    };
    var m = map[status] || ["planned", status];
    return '<span class="badge ' + m[0] + '">' + esc(m[1]) + "</span>";
  }

  function opBadge(op) {
    return '<span class="badge ' + op.toLowerCase() + '">' + esc(op) + "</span>";
  }

  function pct(done, total) { return total ? Math.round((done / total) * 100) : 0; }

  function plural(n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); }

  /* ---------------- sidebar ---------------- */

  function buildNav() {
    var html = '<div class="nav-group">Project</div>';
    html += navItem("overview", "Overview", null, null);
    html += navItem("history", "Change history", null, null);
    html += navItem("diff", "Compare versions", null, null);
    html += '<div class="nav-group">Pillars</div>';
    pillars().forEach(function (p, i) {
      html += navItem("pillar/" + p.id, p.title, i + 1, p.status);
    });
    nav.innerHTML = html;
    nav.querySelectorAll(".nav-item").forEach(function (btn) {
      btn.addEventListener("click", function () {
        go(btn.getAttribute("data-route"));
        document.getElementById("sidebar").classList.remove("open");
      });
    });
  }

  function navItem(route, label, num, status) {
    return '<button class="nav-item" data-route="' + esc(route) + '">' +
      (num ? '<span class="nav-num">' + num + "</span>" : '<span class="nav-num"></span>') +
      '<span class="nav-label">' + esc(label) + "</span>" +
      (status ? '<span class="dot ' + esc(status) + '" title="' + esc(status) + '"></span>' : "") +
      "</button>";
  }

  function markNav() {
    nav.querySelectorAll(".nav-item").forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-route") === state.route);
    });
  }

  /* ---------------- routing ---------------- */

  function go(route) {
    state.route = route;
    if (location.hash.slice(1) !== route) location.hash = route;
    render();
  }

  function render() {
    markNav();
    if (state.compare) { renderDiff(); }
    else if (state.route === "overview") { renderOverview(); }
    else if (state.route === "history") { renderHistory(); }
    else if (state.route === "diff") { renderDiffPicker(); }
    else if (state.route.indexOf("pillar/") === 0) {
      var p = pillarById(state.route.slice(7));
      if (p) renderPillar(p); else renderOverview();
    } else { renderOverview(); }
    view.scrollTop = 0;
    window.scrollTo(0, 0);
  }

  /* ---------------- overview ---------------- */

  function renderOverview() {
    var d = data(), s = d.stats;
    var html = '<div class="page-head">' +
      '<div class="eyebrow">' + esc(d.project.full_name) + "</div>" +
      "<h1>How " + esc(d.project.name) + " works</h1>" +
      '<p class="tagline">' + esc(d.project.tagline) + "</p></div>";

    html += '<div class="stat-grid">' +
      stat(s.pillars, "Pillars", s.pillars_shipped + " fully shipped") +
      stat(s.changes_shipped + "/" + s.changes_total, "Spec changes shipped",
           s.changes_in_flight + " in flight, " + s.changes_not_started + " not started") +
      stat(s.tasks_done, "Tasks completed", "of " + s.tasks_total + " (" + pct(s.tasks_done, s.tasks_total) + "%)") +
      stat(s.scenarios, "Spec scenarios", s.requirements + " requirements") +
      stat(s.known_gaps, "Known gaps", "documented, not hidden") +
      "</div>";

    html += '<h2 class="section">The system at a glance</h2>';
    html += '<div class="diagram-wrap" id="diagram"></div>';
    html += '<div class="legend">' +
      '<span><i class="swatch pillar"></i> Service / pillar — click any box to open it</span>' +
      '<span><i class="swatch store"></i> Data store</span>' +
      '<span><i class="swatch external"></i> Outside openCG</span>' +
      '<span><i class="swatch notyet"></i> Not built yet</span>' +
      "</div>";
    html += '<p class="diagram-note">' + esc(d.diagram.note) + "</p>";

    html += '<h2 class="section">The short version</h2>';
    html += '<div class="callout">Ingestion clones a repo and splits files into chunks. Each chunk is ' +
      "stored in Postgres (the truth) and Qdrant (the index), and simultaneously feeds an extractor that " +
      "builds a concept graph — deterministically for code, with an LLM for prose. When an AI tool asks a " +
      "question over MCP, the pipeline embeds it, searches Postgres and Qdrant in parallel, fuses the two " +
      "rankings, trims to a token budget, and returns the fragments — writing an immutable audit row on the " +
      "way out. <strong>Every pillar below is one stage of that sentence.</strong></div>";

    html += '<h2 class="section">Pillars</h2><div class="card-grid">';
    pillars().forEach(function (p) {
      html += '<button class="pillar-card" data-go="pillar/' + esc(p.id) + '">' +
        '<div class="pc-head"><h3>' + esc(p.title) + "</h3>" + statusBadge(p.status) + "</div>" +
        '<p class="pc-tag">' + raw(p.tagline) + "</p>" +
        '<div class="pc-meta">' +
        "<span>" + plural(p.flow.length, "step") + "</span>" +
        "<span>" + plural(p.change_count, "spec change") + "</span>" +
        "<span>" + plural(p.gaps.length, "gap") + "</span>" +
        "</div></button>";
    });
    html += "</div>";

    view.innerHTML = html;
    drawDiagram(document.getElementById("diagram"), d.diagram);
    wireGoButtons();
  }

  function stat(value, label, sub) {
    return '<div class="stat"><div class="stat-value">' + esc(value) + "</div>" +
      '<div class="stat-label">' + esc(label) + "</div>" +
      (sub ? '<div class="stat-sub">' + esc(sub) + "</div>" : "") + "</div>";
  }

  /* ---------------- diagram ---------------- */

  function drawDiagram(host, dg) {
    if (!host) return;
    var W = dg.node_width, H = dg.node_height;
    var byId = {};
    dg.nodes.forEach(function (n) { byId[n.id] = n; });

    var svg = ['<svg viewBox="0 0 ' + dg.width + " " + dg.height + '" role="img" aria-label="System overview">'];
    svg.push('<defs><marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
      '<path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker></defs>');

    (dg.groups || []).forEach(function (g) {
      svg.push('<rect class="dg-group" x="' + g.x + '" y="' + g.y + '" width="' + g.width +
        '" height="' + g.height + '" rx="12"/>');
      svg.push('<text class="dg-group-label" x="' + (g.x + g.width / 2) + '" y="' + (g.y + 17) +
        '" text-anchor="middle">' + esc(g.label) + "</text>");
    });

    // Edges before boxes so the boxes paint over the line ends.
    var labels = [];
    dg.edges.forEach(function (e) {
      var a = byId[e.from], b = byId[e.to];
      if (!a || !b) return;
      var p = anchors(a, b, W, H);
      svg.push('<path class="dg-edge' + (e.dashed ? " dashed" : "") + '" marker-end="url(#arw)" d="M' +
        p.x1 + "," + p.y1 + " Q" + p.cx + "," + p.cy + " " + p.x2 + "," + p.y2 + '"/>');
      if (!e.label) return;
      // Midpoint of the quadratic curve at t=0.5, so the label sits on the line
      // rather than on the straight chord between the endpoints.
      var mx = (p.x1 + 2 * p.cx + p.x2) / 4;
      var my = (p.y1 + 2 * p.cy + p.y2) / 4;
      labels.push({ x: mx, y: my, text: e.label, dashed: !!e.dashed });
    });

    // Labels last, each on an opaque plate, so nothing has to be read through a line.
    labels.forEach(function (l) {
      var w = l.text.length * 5.9 + 10;
      svg.push('<rect class="dg-edge-plate" x="' + (l.x - w / 2) + '" y="' + (l.y - 8) +
        '" width="' + w + '" height="15" rx="4"/>');
      svg.push('<text class="dg-edge-label' + (l.dashed ? " dashed" : "") + '" x="' + l.x +
        '" y="' + (l.y + 3.5) + '" text-anchor="middle">' + esc(l.text) + "</text>");
    });

    dg.nodes.forEach(function (n) {
      var clickable = n.pillar ? ' data-go="pillar/' + esc(n.pillar) + '" tabindex="0" role="button"' : "";
      svg.push('<g class="dg-node ' + esc(n.kind) + '"' + clickable + '>');
      svg.push('<rect x="' + n.x + '" y="' + n.y + '" width="' + W + '" height="' + H + '"/>');
      svg.push('<text class="dg-label" x="' + (n.x + W / 2) + '" y="' + (n.y + 24) +
        '" text-anchor="middle">' + esc(n.label) + "</text>");
      if (n.sub) {
        svg.push('<text class="dg-sub" x="' + (n.x + W / 2) + '" y="' + (n.y + 40) +
          '" text-anchor="middle">' + esc(n.sub) + "</text>");
      }
      svg.push("</g>");
    });

    svg.push("</svg>");
    host.innerHTML = svg.join("");

    host.querySelectorAll("[data-go]").forEach(function (g) {
      g.addEventListener("click", function () { go(g.getAttribute("data-go")); });
      g.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); go(g.getAttribute("data-go")); }
      });
    });
  }

  /* Pick which side of each box an edge leaves from, so the renderer stays
   * generic and boxes can be moved freely in diagram.py. Boxes on different
   * rows connect top-to-bottom; boxes on the same row connect side-to-side.
   * Comparing the vertical gap against the box height reads "different row"
   * far more reliably than comparing dx against dy. */
  function anchors(a, b, W, H) {
    var ac = { x: a.x + W / 2, y: a.y + H / 2 };
    var bc = { x: b.x + W / 2, y: b.y + H / 2 };
    var dx = bc.x - ac.x, dy = bc.y - ac.y;
    var vertical = Math.abs(dy) > H;
    var p = {};
    if (vertical) {
      p.x1 = ac.x;
      p.y1 = dy > 0 ? a.y + H : a.y;
      p.x2 = bc.x;
      p.y2 = dy > 0 ? b.y : b.y + H;
    } else {
      p.x1 = dx > 0 ? a.x + W : a.x;
      p.y1 = ac.y;
      p.x2 = dx > 0 ? b.x : b.x + W;
      p.y2 = bc.y;
    }
    // Bow the curve slightly perpendicular to its run so parallel edges separate.
    var mx = (p.x1 + p.x2) / 2, my = (p.y1 + p.y2) / 2;
    var bow = Math.min(22, Math.hypot(p.x2 - p.x1, p.y2 - p.y1) * 0.1);
    if (vertical) { p.cx = mx + bow; p.cy = my; }
    else { p.cx = mx; p.cy = my - bow; }
    return p;
  }

  /* ---------------- pillar ---------------- */

  function renderPillar(p) {
    var idx = pillars().indexOf(p) + 1;
    var html = '<div class="page-head">' +
      '<div class="eyebrow">Pillar ' + idx + " of " + pillars().length + "</div>" +
      "<h1>" + esc(p.title) + "</h1>" +
      '<p class="tagline">' + raw(p.tagline) + "</p>" +
      '<div class="badge-row" style="margin-top:12px">' + statusBadge(p.status) +
      p.capabilities.map(function (c) { return '<span class="badge cap">' + esc(c) + "</span>"; }).join("") +
      "</div></div>";

    html += '<div class="stat-grid">' +
      stat(p.flow.length, "Flow steps", null) +
      stat(p.change_count, "Spec changes", p.shipped_change_count + " shipped") +
      stat(p.requirement_count, "Requirements touched", p.scenario_count + " scenarios") +
      stat(p.gaps.length, "Known gaps", null) +
      "</div>";

    if (p.what) { html += '<h2 class="section">What it is</h2><div class="prose">' + raw(p.what) + "</div>"; }
    if (p.why) { html += '<h2 class="section">Why it exists</h2><div class="prose">' + raw(p.why) + "</div>"; }

    if (p.flow.length) {
      html += '<h2 class="section">How it works, end to end</h2>';
      html += '<p class="prose" style="margin-bottom:14px;font-size:13.5px">Click any step to see the ' +
        "mechanical detail and the file that implements it.</p>";
      html += '<div class="stepper">';
      p.flow.forEach(function (st) {
        var key = p.id + ":" + st.index;
        var open = !!state.openSteps[key];
        html += '<div class="step' + (open ? " open" : "") + '" data-step="' + esc(key) + '">' +
          '<button class="step-btn" type="button">' +
          '<span class="step-num">' + st.index + "</span>" +
          '<span class="step-title">' + raw(st.title) + "</span>" +
          '<span class="step-chev">▶</span></button>' +
          '<div class="step-body"' + (open ? "" : ' style="display:none"') + ">" + raw(st.detail) +
          (st.files.length ? '<div class="step-files">' + st.files.map(function (f) {
            return '<div class="step-file">' + esc(f) + "</div>";
          }).join("") + "</div>" : "") +
          "</div></div>";
      });
      html += "</div>";
    }

    if (p.facts.length) {
      html += '<h2 class="section">Key facts</h2><ul class="fact-list">' +
        p.facts.map(function (f) { return "<li><span>" + raw(f) + "</span></li>"; }).join("") + "</ul>";
    }

    if (p.gaps.length) {
      html += '<h2 class="section">Known gaps and deferred work</h2>';
      html += '<p class="prose" style="margin-bottom:12px;font-size:13.5px">Written from the state of the ' +
        "code, not the aspiration. These are the things this pillar does <em>not</em> do yet.</p>";
      html += '<ul class="gap-list">' +
        p.gaps.map(function (g) { return "<li><span>" + raw(g) + "</span></li>"; }).join("") + "</ul>";
    }

    html += '<h2 class="section">Spec changes that shaped this pillar</h2>';
    if (!p.changes.length) {
      html += '<div class="empty">No OpenSpec change has touched ' +
        p.capabilities.map(function (c) { return "<code>" + esc(c) + "</code>"; }).join(", ") + " yet.</div>";
    } else {
      html += '<p class="prose" style="margin-bottom:14px;font-size:13.5px">Derived automatically from the ' +
        "capability tags in each <code>proposal.md</code> — oldest first, so this reads as the pillar's " +
        "history. Click a change to see the requirements it added or modified here.</p>";
      html += '<div class="timeline">';
      p.changes.slice().reverse().forEach(function (c) {
        html += changeRow(c, p.id, true);
      });
      html += "</div>";
    }

    html += navFooter(p);
    view.innerHTML = html;
    wireSteps(p);
    wireChanges();
    wireGoButtons();
  }

  function navFooter(p) {
    var list = pillars(), i = list.indexOf(p);
    var prev = list[i - 1], next = list[i + 1];
    var html = '<h2 class="section">Keep reading</h2><div class="two-col">';
    html += prev
      ? '<button class="pillar-card" data-go="pillar/' + esc(prev.id) + '"><div class="pc-meta">← Previous</div>' +
        "<h3>" + esc(prev.title) + '</h3><p class="pc-tag">' + raw(prev.tagline) + "</p></button>"
      : '<button class="pillar-card" data-go="overview"><div class="pc-meta">← Back</div>' +
        "<h3>Overview</h3><p class=\"pc-tag\">The whole system on one page.</p></button>";
    html += next
      ? '<button class="pillar-card" data-go="pillar/' + esc(next.id) + '"><div class="pc-meta">Next →</div>' +
        "<h3>" + esc(next.title) + '</h3><p class="pc-tag">' + raw(next.tagline) + "</p></button>"
      : '<button class="pillar-card" data-go="history"><div class="pc-meta">Next →</div>' +
        "<h3>Change history</h3><p class=\"pc-tag\">Every spec change on one timeline.</p></button>";
    return html + "</div>";
  }

  function wireSteps(p) {
    view.querySelectorAll(".step").forEach(function (node) {
      var key = node.getAttribute("data-step");
      node.querySelector(".step-btn").addEventListener("click", function () {
        var open = !state.openSteps[key];
        state.openSteps[key] = open;
        node.classList.toggle("open", open);
        node.querySelector(".step-body").style.display = open ? "" : "none";
      });
    });
  }

  /* ---------------- change rows ---------------- */

  function changeRow(c, scope, showDeltas) {
    var key = (scope || "all") + ":" + c.name;
    var open = !!state.openChanges[key];
    var html = '<div class="change' + (open ? " open" : "") + '" data-change="' + esc(key) + '">' +
      '<button class="change-btn" type="button">' +
      '<span class="change-date">' + esc(c.date || "in flight") + "</span>" +
      '<span class="change-name">' + esc(c.name) +
      (c.introduced ? ' <span class="badge added">introduced</span>' : "") + "</span>" +
      '<span class="change-right">' +
      '<span class="change-tasks">' + c.tasks_done + "/" + c.tasks_total + "</span>" +
      statusBadge(c.status) + "</span></button>";

    html += '<div class="change-body"' + (open ? "" : ' style="display:none"') + ">";
    if (c.why) html += '<p class="change-why">' + esc(c.why) + "</p>";

    if (c.tasks_total) {
      html += '<div class="bar"><i class="' + (c.status === "shipped" ? "ok" : "warn") +
        '" style="width:' + pct(c.tasks_done, c.tasks_total) + '%"></i></div>';
    }

    if (showDeltas && c.deltas && c.deltas.length) {
      var groups = {};
      c.deltas.forEach(function (d) { (groups[d.capability] = groups[d.capability] || []).push(d); });
      html += '<div class="subhead">Requirements this change touched here</div>';
      Object.keys(groups).sort().forEach(function (cap) {
        html += '<div class="delta-group"><div class="delta-cap">' + esc(cap) + "</div>";
        groups[cap].forEach(function (d) {
          html += '<div class="delta">' + opBadge(d.operation) + "<span>" + esc(d.requirement) +
            (d.scenarios.length ? '<span class="delta-scenarios"> · ' +
              plural(d.scenarios.length, "scenario") + "</span>" : "") + "</span></div>";
        });
        html += "</div>";
      });
    }

    if (c.what_changes && c.what_changes.length) {
      html += '<div class="subhead">What changed</div><ul class="bullet-list">' +
        c.what_changes.slice(0, 8).map(function (b) { return "<li>" + inline(b) + "</li>"; }).join("") +
        (c.what_changes.length > 8
          ? '<li class="delta-scenarios">…and ' + (c.what_changes.length - 8) + " more</li>"
          : "") +
        "</ul>";
    }

    if (c.capabilities_touched && c.capabilities_touched.length) {
      html += '<div class="subhead">Capabilities</div><div class="badge-row">' +
        c.capabilities_touched.map(function (x) {
          return '<span class="badge cap">' + esc(x) + "</span>";
        }).join("") + "</div>";
    }

    if (c.impact && c.impact.length) {
      html += '<div class="subhead">Impact</div><ul class="bullet-list">' +
        c.impact.slice(0, 6).map(function (b) { return "<li>" + inline(b) + "</li>"; }).join("") + "</ul>";
    }

    return html + "</div></div>";
  }

  // Markdown inline for OpenSpec text, which the Python side leaves as raw markdown.
  function inline(s) {
    return esc(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }

  function wireChanges() {
    view.querySelectorAll(".change").forEach(function (node) {
      var key = node.getAttribute("data-change");
      node.querySelector(".change-btn").addEventListener("click", function () {
        var open = !state.openChanges[key];
        state.openChanges[key] = open;
        node.classList.toggle("open", open);
        node.querySelector(".change-body").style.display = open ? "" : "none";
      });
    });
  }

  /* ---------------- history ---------------- */

  function renderHistory() {
    var d = data(), s = d.stats;
    var caps = {};
    d.changes.forEach(function (c) {
      c.capabilities_new.concat(c.capabilities_modified).forEach(function (x) {
        caps[x] = (caps[x] || 0) + 1;
      });
    });

    var html = '<div class="page-head"><div class="eyebrow">Project history</div>' +
      "<h1>Every spec change</h1>" +
      '<p class="tagline">Each entry is one OpenSpec change: a proposal, a design, testable scenarios, ' +
      "and a task list. Nothing gets built here without one.</p></div>";

    html += '<div class="stat-grid">' +
      stat(s.changes_total, "Changes", s.changes_shipped + " shipped") +
      stat(s.tasks_done + "/" + s.tasks_total, "Tasks", pct(s.tasks_done, s.tasks_total) + "% complete") +
      stat(s.capabilities, "Capabilities", "tracked across " + s.pillars + " pillars") +
      stat(s.scenarios, "Scenarios", "in the archived baseline") +
      "</div>";

    html += '<h2 class="section">Filter by capability</h2><div class="filter-row">';
    html += '<button class="chip' + (state.changeFilter ? "" : " on") + '" data-filter="">All</button>';
    Object.keys(caps).sort().forEach(function (c) {
      html += '<button class="chip' + (state.changeFilter === c ? " on" : "") +
        '" data-filter="' + esc(c) + '">' + esc(c) + " <span style=\"opacity:.6\">" + caps[c] + "</span></button>";
    });
    html += "</div>";

    var shown = d.changes.filter(function (c) {
      if (!state.changeFilter) return true;
      return c.capabilities_new.concat(c.capabilities_modified).indexOf(state.changeFilter) !== -1;
    });

    var active = shown.filter(function (c) { return !c.archived; });
    var archived = shown.filter(function (c) { return c.archived; });

    if (active.length) {
      html += '<h2 class="section">In flight</h2><div class="timeline">' +
        active.map(function (c) { return changeRow(withTouched(c), "all", true); }).join("") + "</div>";
    }
    if (archived.length) {
      html += '<h2 class="section">Shipped and archived — newest first</h2><div class="timeline">' +
        archived.map(function (c) { return changeRow(withTouched(c), "all", true); }).join("") + "</div>";
    }
    if (!shown.length) html += '<div class="empty">No change touches that capability.</div>';

    view.innerHTML = html;
    view.querySelectorAll("[data-filter]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.changeFilter = btn.getAttribute("data-filter") || null;
        renderHistory();
      });
    });
    wireChanges();
  }

  // The history view shows all of a change's capabilities, not a pillar subset.
  function withTouched(c) {
    var copy = {};
    for (var k in c) if (Object.prototype.hasOwnProperty.call(c, k)) copy[k] = c[k];
    copy.capabilities_touched = c.capabilities_new.concat(c.capabilities_modified);
    copy.introduced = c.capabilities_new.length > 0;
    return copy;
  }

  /* ---------------- diff ---------------- */

  function renderDiffPicker() {
    var html = '<div class="page-head"><div class="eyebrow">Version history</div>' +
      "<h1>Compare versions</h1>" +
      '<p class="tagline">Every rebuild that changed content wrote a snapshot. Pick two to see exactly ' +
      "what moved between them.</p></div>";

    if (VERSIONS.length < 2) {
      html += '<div class="empty">Only one version exists so far (<b>' + esc(LATEST.label) +
        "</b>, " + esc(LATEST.date) + ").<br>Run <code>make explainer</code> after your next change and a " +
        "second snapshot will appear here automatically.</div>";
    } else {
      html += '<p class="prose" style="margin-bottom:14px">Use the <strong>Compare with</strong> picker in ' +
        "the top bar, or choose a pair below.</p><div class=\"timeline\">";
      for (var i = VERSIONS.length - 1; i > 0; i--) {
        var b = VERSIONS[i], a = VERSIONS[i - 1];
        html += '<button class="pillar-card" data-pair="' + a.seq + ":" + b.seq + '">' +
          '<div class="pc-head"><h3>' + esc(a.label) + " → " + esc(b.label) + "</h3>" +
          '<span class="badge modified">diff</span></div>' +
          '<p class="pc-tag">' + esc(a.date) + " → " + esc(b.date) + "</p>" +
          '<div class="pc-meta"><span>' + b.summary.pillars + " pillars</span><span>" +
          b.summary.changes_shipped + " shipped changes</span><span>" +
          b.summary.tasks_done + " tasks done</span></div></button>";
      }
      html += "</div>";
    }

    html += '<h2 class="section">All versions</h2><div class="table-wrap"><table>' +
      "<thead><tr><th>Version</th><th>Date</th><th>Pillars</th><th>Shipped changes</th>" +
      "<th>Tasks done</th><th>Gaps</th><th>Content hash</th></tr></thead><tbody>";
    VERSIONS.slice().reverse().forEach(function (v) {
      html += "<tr><td><b>" + esc(v.label) + "</b></td><td class=\"num\">" + esc(v.date) + "</td>" +
        '<td class="num">' + v.summary.pillars + "</td>" +
        '<td class="num">' + v.summary.changes_shipped + "/" + v.summary.changes_total + "</td>" +
        '<td class="num">' + v.summary.tasks_done + "/" + v.summary.tasks_total + "</td>" +
        '<td class="num">' + v.summary.known_gaps + "</td>" +
        '<td class="num">' + esc(v.hash.slice(0, 12)) + "</td></tr>";
    });
    html += "</tbody></table></div>";

    view.innerHTML = html;
    view.querySelectorAll("[data-pair]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var parts = btn.getAttribute("data-pair").split(":");
        setCompare(Number(parts[0]), Number(parts[1]));
      });
    });
  }

  function setCompare(baseSeq, headSeq) {
    state.compare = bySeq(baseSeq);
    state.version = bySeq(headSeq);
    document.getElementById("version-select").value = String(headSeq);
    document.getElementById("compare-select").value = String(baseSeq);
    state.route = "diff";
    location.hash = "diff";
    render();
  }

  function bySeq(seq) {
    for (var i = 0; i < VERSIONS.length; i++) if (VERSIONS[i].seq === seq) return VERSIONS[i];
    return null;
  }

  function renderDiff() {
    var A = state.compare, B = state.version;
    var a = A.data, b = B.data;

    var html = '<div class="page-head"><div class="eyebrow">Comparing versions</div>' +
      "<h1>What changed</h1></div>";

    html += '<div class="diff-head"><span class="vtag">' + esc(A.label) + " · " + esc(A.date) + "</span>" +
      '<span class="diff-arrow">→</span><span class="vtag">' + esc(B.label) + " · " + esc(B.date) + "</span>" +
      '<button class="chip" id="exit-diff" style="margin-left:auto">Exit diff</button></div>';

    if (A.seq === B.seq) {
      view.innerHTML = html + '<div class="empty">Those are the same version.</div>';
      document.getElementById("exit-diff").addEventListener("click", exitDiff);
      return;
    }

    html += '<h2 class="section">Numbers</h2><div class="diff-stat-row">';
    [["pillars", "Pillars"], ["changes_shipped", "Shipped changes"], ["changes_total", "Total changes"],
     ["tasks_done", "Tasks done"], ["scenarios", "Scenarios"], ["requirements", "Requirements"],
     ["known_gaps", "Known gaps"], ["flow_steps", "Flow steps"]].forEach(function (pair) {
      var k = pair[0];
      var av = a.stats[k], bv = b.stats[k];
      if (av === undefined || bv === undefined) return;
      html += '<div class="diff-stat">' + esc(pair[1]) + ": <b>" + bv + "</b> " + deltaTag(bv - av) + "</div>";
    });
    html += "</div>";

    // Pillars added / removed / changed.
    var aP = index(a.pillars), bP = index(b.pillars);
    var added = b.pillars.filter(function (p) { return !aP[p.id]; });
    var removed = a.pillars.filter(function (p) { return !bP[p.id]; });

    if (added.length) {
      html += '<h2 class="section">Pillars added</h2>';
      added.forEach(function (p) {
        html += '<div class="diff-block"><h4><span class="badge added">new</span>' + esc(p.title) +
          '</h4><div class="difflines">' + p.flow.map(function (s) {
            return '<div class="add"><span class="sign">+</span>' + esc(s.index + ". " + stripTags(s.title)) + "</div>";
          }).join("") + "</div></div>";
      });
    }
    if (removed.length) {
      html += '<h2 class="section">Pillars removed</h2>';
      removed.forEach(function (p) {
        html += '<div class="diff-block"><h4><span class="badge removed">gone</span>' +
          esc(p.title) + "</h4></div>";
      });
    }

    var changedBlocks = [];
    b.pillars.forEach(function (p) {
      var old = aP[p.id];
      if (!old) return;
      var lines = pillarLines(old), next = pillarLines(p);
      if (lines.join("\n") === next.join("\n")) return;
      changedBlocks.push('<div class="diff-block"><h4><span class="badge modified">changed</span>' +
        esc(p.title) + "</h4>" + diffHtml(lines, next) + "</div>");
    });

    html += '<h2 class="section">Pillar content changes</h2>';
    html += changedBlocks.length ? changedBlocks.join("")
      : '<div class="empty">No pillar description, flow step, fact, or gap changed between these versions.</div>';

    // Spec changes gained between snapshots.
    var aC = index(a.changes, "name"), bC = index(b.changes, "name");
    var newChanges = b.changes.filter(function (c) { return !aC[c.name]; });
    var progressed = b.changes.filter(function (c) {
      var old = aC[c.name];
      return old && (old.tasks_done !== c.tasks_done || old.status !== c.status);
    });

    html += '<h2 class="section">Spec changes</h2>';
    if (!newChanges.length && !progressed.length) {
      html += '<div class="empty">No spec change was added or progressed between these versions.</div>';
    } else {
      html += '<div class="timeline">';
      newChanges.forEach(function (c) {
        html += '<div class="diff-block"><h4><span class="badge added">new</span>' +
          '<span class="change-name">' + esc(c.name) + "</span>" + statusBadge(c.status) +
          '<span class="change-tasks" style="margin-left:auto">' + c.tasks_done + "/" + c.tasks_total +
          "</span></h4>" + (c.why ? '<div style="padding:11px 15px" class="change-why">' +
          esc(c.why) + "</div>" : "") + "</div>";
      });
      progressed.forEach(function (c) {
        var old = aC[c.name];
        html += '<div class="diff-block"><h4><span class="badge modified">progressed</span>' +
          '<span class="change-name">' + esc(c.name) + "</span>" +
          '<span class="change-tasks" style="margin-left:auto">' + old.tasks_done + " → " +
          c.tasks_done + " / " + c.tasks_total + " " + deltaTag(c.tasks_done - old.tasks_done) +
          "</span></h4>" +
          (old.status !== c.status
            ? '<div style="padding:11px 15px">' + statusBadge(old.status) +
              ' <span class="diff-arrow">→</span> ' + statusBadge(c.status) + "</div>"
            : "") +
          "</div>";
      });
      html += "</div>";
    }

    view.innerHTML = html;
    document.getElementById("exit-diff").addEventListener("click", exitDiff);
  }

  function exitDiff() {
    state.compare = null;
    document.getElementById("compare-select").value = "";
    go("overview");
  }

  function deltaTag(n) {
    if (n > 0) return '<span class="delta-up">+' + n + "</span>";
    if (n < 0) return '<span class="delta-down">' + n + "</span>";
    return '<span class="delta-flat">±0</span>';
  }

  function index(list, key) {
    var out = {};
    (list || []).forEach(function (x) { out[x[key || "id"]] = x; });
    return out;
  }

  // Flatten a pillar into comparable lines so a text diff can show what moved.
  function pillarLines(p) {
    var lines = [];
    lines.push("status: " + p.status);
    lines.push("tagline: " + stripTags(p.tagline));
    if (p.what) lines.push("what: " + stripTags(p.what));
    if (p.why) lines.push("why: " + stripTags(p.why));
    p.flow.forEach(function (s) {
      lines.push("step " + s.index + ": " + stripTags(s.title));
      if (s.detail) lines.push("    " + stripTags(s.detail));
      s.files.forEach(function (f) { lines.push("    file: " + f); });
    });
    p.facts.forEach(function (f) { lines.push("fact: " + stripTags(f)); });
    p.gaps.forEach(function (g) { lines.push("gap: " + stripTags(g)); });
    return lines;
  }

  /* Classic LCS diff. Inputs are small (tens of lines per pillar), so the
   * O(n*m) table is fine and keeps the implementation obvious. */
  function diffHtml(a, b) {
    var n = a.length, m = b.length;
    var lcs = [];
    for (var i = 0; i <= n; i++) { lcs.push(new Array(m + 1).fill(0)); }
    for (i = n - 1; i >= 0; i--) {
      for (var j = m - 1; j >= 0; j--) {
        lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
      }
    }
    var rows = [];
    i = 0; j = 0;
    while (i < n && j < m) {
      if (a[i] === b[j]) { rows.push(["ctx", " ", a[i]]); i++; j++; }
      else if (lcs[i + 1][j] >= lcs[i][j + 1]) { rows.push(["del", "-", a[i]]); i++; }
      else { rows.push(["add", "+", b[j]]); j++; }
    }
    while (i < n) { rows.push(["del", "-", a[i++]]); }
    while (j < m) { rows.push(["add", "+", b[j++]]); }

    // Collapse long unchanged runs so the changes stay visible.
    var out = [], run = 0;
    function flushRun() {
      if (run > 4) out.splice(out.length - 2, run - 4,
        '<div class="skip"><span class="sign"> </span>… ' + (run - 4) + " unchanged lines …</div>");
      run = 0;
    }
    rows.forEach(function (r) {
      if (r[0] === "ctx") { run++; } else { flushRun(); }
      out.push('<div class="' + r[0] + '"><span class="sign">' + r[1] + "</span>" + esc(r[2]) + "</div>");
    });
    flushRun();
    return '<div class="difflines">' + out.join("") + "</div>";
  }

  /* ---------------- search ---------------- */

  function buildSearchIndex() {
    var rows = [], d = data();
    d.pillars.forEach(function (p) {
      rows.push({ kind: "pillar", label: p.title, sub: stripTags(p.tagline), route: "pillar/" + p.id,
                  hay: (p.title + " " + stripTags(p.tagline) + " " + stripTags(p.what) + " " +
                        stripTags(p.why) + " " + p.capabilities.join(" ")).toLowerCase() });
      p.flow.forEach(function (s) {
        rows.push({ kind: "step", label: stripTags(s.title), sub: p.title + " · step " + s.index,
                    route: "pillar/" + p.id, step: p.id + ":" + s.index,
                    hay: (stripTags(s.title) + " " + stripTags(s.detail) + " " + s.files.join(" ")).toLowerCase() });
      });
      p.gaps.forEach(function (g) {
        rows.push({ kind: "gap", label: stripTags(g).slice(0, 96), sub: p.title + " · known gap",
                    route: "pillar/" + p.id, hay: stripTags(g).toLowerCase() });
      });
      p.facts.forEach(function (f) {
        rows.push({ kind: "fact", label: stripTags(f).slice(0, 96), sub: p.title + " · fact",
                    route: "pillar/" + p.id, hay: stripTags(f).toLowerCase() });
      });
    });
    d.changes.forEach(function (c) {
      rows.push({ kind: "change", label: c.name, sub: (c.date || "in flight") + " · " + c.status,
                  route: "history", change: "all:" + c.name,
                  hay: (c.name + " " + c.why + " " + c.what_changes.join(" ")).toLowerCase() });
    });
    return rows;
  }

  var searchIndex = null;

  function runSearch(q) {
    var box = document.getElementById("search-results");
    q = q.trim().toLowerCase();
    if (q.length < 2) { box.hidden = true; state.searchHits = []; return; }
    if (!searchIndex) searchIndex = buildSearchIndex();

    var hits = searchIndex.filter(function (r) { return r.hay.indexOf(q) !== -1; });
    hits.sort(function (x, y) {
      var xa = x.label.toLowerCase().indexOf(q) === 0 ? 0 : 1;
      var ya = y.label.toLowerCase().indexOf(q) === 0 ? 0 : 1;
      return xa - ya;
    });
    hits = hits.slice(0, 24);
    state.searchHits = hits;
    state.searchSel = 0;

    if (!hits.length) {
      box.innerHTML = '<div class="search-empty">Nothing matches “' + esc(q) + "”.</div>";
    } else {
      box.innerHTML = hits.map(function (r, i) {
        return '<button class="search-hit' + (i === 0 ? " sel" : "") + '" data-i="' + i + '">' +
          '<span class="hit-kind">' + esc(r.kind) + "</span>" + esc(r.label) +
          '<span class="hit-sub">' + esc(r.sub) + "</span></button>";
      }).join("");
      box.querySelectorAll(".search-hit").forEach(function (btn) {
        btn.addEventListener("click", function () { openHit(hits[Number(btn.getAttribute("data-i"))]); });
      });
    }
    box.hidden = false;
  }

  function openHit(hit) {
    if (!hit) return;
    if (hit.step) state.openSteps[hit.step] = true;
    if (hit.change) state.openChanges[hit.change] = true;
    document.getElementById("search-results").hidden = true;
    document.getElementById("search").value = "";
    go(hit.route);
    if (hit.step) {
      var node = view.querySelector('[data-step="' + hit.step + '"]');
      if (node) node.scrollIntoView({ block: "center" });
    }
  }

  /* ---------------- top bar ---------------- */

  function buildPickers() {
    var vs = document.getElementById("version-select");
    var cs = document.getElementById("compare-select");
    var opts = VERSIONS.slice().reverse().map(function (v) {
      return '<option value="' + v.seq + '">' + esc(v.label) + " · " + esc(v.date) + "</option>";
    }).join("");
    vs.innerHTML = opts;
    cs.innerHTML = '<option value="">none</option>' + opts;
    vs.value = String(state.version.seq);

    vs.addEventListener("change", function () {
      state.version = bySeq(Number(vs.value));
      searchIndex = null;
      buildNav();
      if (state.compare && state.compare.seq === state.version.seq) {
        state.compare = null;
        cs.value = "";
      }
      render();
    });
    cs.addEventListener("change", function () {
      var seq = cs.value ? Number(cs.value) : null;
      state.compare = seq ? bySeq(seq) : null;
      if (state.compare) { state.route = "diff"; location.hash = "diff"; }
      render();
    });
  }

  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem("opencg-explainer-theme"); } catch (e) { /* file:// */ }
    if (saved) document.documentElement.setAttribute("data-theme", saved);
    document.getElementById("theme-btn").addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("opencg-explainer-theme", next); } catch (e) { /* ignore */ }
    });
  }

  function wireGoButtons() {
    view.querySelectorAll("[data-go]").forEach(function (btn) {
      if (btn.tagName === "BUTTON" || btn.hasAttribute("data-go")) {
        btn.addEventListener("click", function () { go(btn.getAttribute("data-go")); });
      }
    });
  }

  function initSearch() {
    var input = document.getElementById("search");
    var box = document.getElementById("search-results");
    input.addEventListener("input", function () { runSearch(input.value); });
    input.addEventListener("keydown", function (ev) {
      if (!state.searchHits.length) return;
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        state.searchSel = Math.max(0, Math.min(state.searchHits.length - 1,
          state.searchSel + (ev.key === "ArrowDown" ? 1 : -1)));
        box.querySelectorAll(".search-hit").forEach(function (b, i) {
          b.classList.toggle("sel", i === state.searchSel);
          if (i === state.searchSel) b.scrollIntoView({ block: "nearest" });
        });
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        openHit(state.searchHits[state.searchSel]);
      } else if (ev.key === "Escape") {
        box.hidden = true; input.value = "";
      }
    });
    document.addEventListener("click", function (ev) {
      if (!ev.target.closest(".search-wrap")) box.hidden = true;
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "/" && document.activeElement !== input) { ev.preventDefault(); input.focus(); }
    });
  }

  /* ---------------- boot ---------------- */

  function boot() {
    document.getElementById("foot-version").textContent =
      LATEST.label + " · " + LATEST.date + " · " + VERSIONS.length +
      (VERSIONS.length === 1 ? " version" : " versions");
    document.getElementById("foot-generated").textContent =
      "built " + (PAYLOAD.generated_at || "").replace("T", " ").replace("+00:00", " UTC");

    document.getElementById("menu-btn").addEventListener("click", function () {
      document.getElementById("sidebar").classList.toggle("open");
    });

    initTheme();
    buildNav();
    buildPickers();
    initSearch();

    var hash = location.hash.slice(1);
    state.route = hash || "overview";
    window.addEventListener("hashchange", function () {
      var h = location.hash.slice(1) || "overview";
      if (h !== state.route) { state.route = h; render(); }
    });

    render();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
