/* Runtime smoke test for the generated explainer.
 *
 *   node tools/explainer/tests/smoke_render.js
 *
 * Boots app.js against a minimal DOM shim and renders every route for every
 * version. Catches the class of bug `node --check` cannot: bad property access,
 * undefined data fields, and exceptions thrown while building markup.
 *
 * Phase 2 injects a synthetic second version so the compare/diff paths are
 * exercised even when only one real snapshot exists on disk.
 *
 * The shim deliberately does not implement an HTML parser — element queries
 * return empty lists. That is enough to exercise all of the string building,
 * which is where the risk lives, without pulling in jsdom.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const REPO = path.resolve(__dirname, "../../..");
const HTML = path.join(REPO, "docs/explainer/index.html");

if (!fs.existsSync(HTML)) {
  console.error("no build to test; run: make explainer");
  process.exit(1);
}

const html = fs.readFileSync(HTML, "utf8");

const dataMatch = html.match(
  /<script id="explainer-data" type="application\/json">([\s\S]*?)<\/script>/
);
const jsMatch = html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/);
if (!dataMatch || !jsMatch) {
  console.error("could not extract the data payload or app script from index.html");
  process.exit(1);
}

const APP_SOURCE = jsMatch[1];
const realPayload = JSON.parse(dataMatch[1].replace(/<\\\//g, "</"));
if (!realPayload.versions || !realPayload.versions.length) {
  console.error("payload contains no versions");
  process.exit(1);
}

const failures = [];

function attempt(label, fn) {
  try {
    fn();
  } catch (err) {
    failures.push(label + ": " + (err && err.message ? err.message : String(err)));
  }
}

/* ---------- minimal DOM ---------- */

function makeHarness(payload) {
  let renderCount = 0;
  const nodes = {};

  function firstBadSnippet(v) {
    const m = v.match(/.{0,60}(undefined|\[object Object\]|NaN).{0,60}/);
    return m ? m[0].replace(/\s+/g, " ") : "?";
  }

  function makeEl(id) {
    const listeners = {};
    return {
      id: id || "",
      tagName: "DIV",
      textContent: "",
      value: "",
      hidden: false,
      scrollTop: 0,
      _html: "",
      get innerHTML() { return this._html; },
      set innerHTML(v) {
        if (typeof v !== "string") throw new Error("innerHTML set to non-string on #" + this.id);
        if (/undefined|\[object Object\]|NaN/.test(v)) {
          throw new Error("suspicious markup on #" + this.id + ": " + firstBadSnippet(v));
        }
        this._html = v;
        renderCount++;
      },
      classList: {
        _set: new Set(),
        add(c) { this._set.add(c); },
        remove(c) { this._set.delete(c); },
        contains(c) { return this._set.has(c); },
        toggle(c, on) {
          if (on === undefined) on = !this._set.has(c);
          if (on) this._set.add(c); else this._set.delete(c);
        }
      },
      addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
      removeEventListener() {},
      setAttribute(k, v) { this["attr_" + k] = String(v); },
      getAttribute(k) {
        return Object.prototype.hasOwnProperty.call(this, "attr_" + k) ? this["attr_" + k] : null;
      },
      hasAttribute(k) { return Object.prototype.hasOwnProperty.call(this, "attr_" + k); },
      querySelector() { return null; },
      querySelectorAll() { return []; },
      scrollIntoView() {},
      focus() {},
      closest() { return null; },
      _fire(type, ev) { (listeners[type] || []).forEach((fn) => fn(ev || {})); }
    };
  }

  function byId(id) {
    if (!nodes[id]) nodes[id] = makeEl(id);
    return nodes[id];
  }

  const payloadText = JSON.stringify(payload);
  byId("explainer-data").textContent = payloadText;

  const documentShim = {
    readyState: "complete",
    documentElement: makeEl("html"),
    getElementById: byId,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
    createElement: (tag) => makeEl(tag)
  };
  documentShim.documentElement.setAttribute("data-theme", "dark");

  // A real accessor, so assigning `location.hash` fires hashchange the way the
  // app's router expects.
  const windowListeners = {};
  const locationShim = {
    _hash: "",
    get hash() { return this._hash; },
    set hash(v) {
      const next = v.charAt(0) === "#" ? v : "#" + v;
      if (next === this._hash) return;
      this._hash = next;
      (windowListeners.hashchange || []).forEach((fn) => fn({}));
    }
  };

  const sandbox = {
    document: documentShim,
    location: locationShim,
    localStorage: {
      _v: {},
      getItem(k) { return Object.prototype.hasOwnProperty.call(this._v, k) ? this._v[k] : null; },
      setItem(k, v) { this._v[k] = String(v); }
    },
    window: {
      addEventListener(type, fn) { (windowListeners[type] = windowListeners[type] || []).push(fn); },
      scrollTo: () => {}
    },
    console, Math, JSON, Set, Array, Object, String, Number, Boolean
  };
  sandbox.window.document = documentShim;
  sandbox.window.location = locationShim;
  sandbox.globalThis = sandbox;

  vm.createContext(sandbox);
  vm.runInContext(APP_SOURCE, sandbox, { filename: "app.js" });

  return {
    byId,
    location: locationShim,
    documentElement: documentShim.documentElement,
    view: byId("view"),
    versionSelect: byId("version-select"),
    compareSelect: byId("compare-select"),
    fireChange(el) { el._fire("change", { target: el }); },
    get renders() { return renderCount; }
  };
}

/* ---------- exercise ---------- */

function exercise(label, payload) {
  let h;
  attempt(label + " boot", () => { h = makeHarness(payload); });
  if (!h) return { renders: 0, routes: 0 };

  const seqs = payload.versions.map((v) => v.seq).sort((a, b) => a - b);
  let routeCount = 0;

  seqs.forEach((seq) => {
    const snapshot = payload.versions.filter((v) => v.seq === seq)[0];
    // Routes are per-version: a pillar can exist in one snapshot and not another.
    const routes = ["overview", "history", "diff"].concat(
      snapshot.data.pillars.map((p) => "pillar/" + p.id)
    );
    routeCount += routes.length;

    attempt(label + " select v" + seq, () => {
      h.compareSelect.value = "";
      h.fireChange(h.compareSelect);
      h.versionSelect.value = String(seq);
      h.fireChange(h.versionSelect);
    });

    routes.forEach((route) => {
      attempt(label + " v" + seq + " " + route, () => {
        // Bounce via a neutral route: the app skips re-rendering the route it
        // is already on.
        h.location.hash = "__probe__";
        h.location.hash = route;

        const markup = h.view.innerHTML;
        if (!markup.length) throw new Error("empty view");

        const expect = {
          overview: "How openCG works",
          history: "Every spec change",
          diff: "Compare versions"
        }[route];
        if (expect && markup.indexOf(expect) === -1) {
          throw new Error('expected "' + expect + '" in rendered view');
        }
        if (route.indexOf("pillar/") === 0) {
          const id = route.slice(7);
          const pillar = snapshot.data.pillars.filter((p) => p.id === id)[0];
          if (!pillar) throw new Error("pillar missing from payload");
          if (markup.indexOf(pillar.title) === -1) {
            throw new Error("view does not mention " + pillar.title);
          }
          if (pillar.flow.length && markup.indexOf("step-num") === -1) {
            throw new Error("flow stepper did not render");
          }
          if (pillar.gaps.length && markup.indexOf("gap-list") === -1) {
            throw new Error("gap list did not render");
          }
        }
      });
    });
  });

  // Diff across every adjacent pair, then a self-diff, which must be handled
  // gracefully rather than thrown.
  for (let i = 1; i < seqs.length; i++) {
    attempt(label + " diff v" + seqs[i - 1] + "->v" + seqs[i], () => {
      h.versionSelect.value = String(seqs[i]);
      h.fireChange(h.versionSelect);
      h.compareSelect.value = String(seqs[i - 1]);
      h.fireChange(h.compareSelect);
      const markup = h.view.innerHTML;
      if (markup.indexOf("What changed") === -1) throw new Error("diff view did not render");
      if (markup.indexOf("difflines") === -1 && markup.indexOf("No pillar") === -1) {
        throw new Error("diff produced neither line diffs nor an empty-state");
      }
    });
  }

  attempt(label + " diff self", () => {
    h.versionSelect.value = String(seqs[0]);
    h.fireChange(h.versionSelect);
    h.compareSelect.value = String(seqs[0]);
    h.fireChange(h.compareSelect);
    if (h.view.innerHTML.indexOf("same version") === -1) {
      throw new Error("self-diff should report the versions are identical");
    }
  });

  attempt(label + " theme toggle", () => {
    h.byId("theme-btn")._fire("click");
    const t = h.documentElement.getAttribute("data-theme");
    if (t !== "light" && t !== "dark") throw new Error("theme not set, got " + t);
  });

  attempt(label + " search", () => {
    const input = h.byId("search");
    ["graph", "token", "qdrant", "audit", "chunk", "zzzznope", "a"].forEach((q) => {
      input.value = q;
      input._fire("input", { target: input });
    });
  });

  return { renders: h.renders, routes: routeCount };
}

/* ---------- phase 1: the real build ---------- */

const realRenders = exercise("real", realPayload);

/* ---------- phase 2: synthetic second version, to exercise diffing ---------- */

function syntheticTwoVersion(base) {
  // Keep only the newest real snapshot, then derive a mutated successor, so the
  // diff assertions below hold no matter how many real versions exist on disk.
  const clone = JSON.parse(JSON.stringify(base));
  clone.versions = [clone.versions[clone.versions.length - 1]];
  const v1 = clone.versions[0];
  const v2 = JSON.parse(JSON.stringify(v1));

  v2.seq = v1.seq + 1;
  v2.label = "v" + v2.seq;
  v2.date = "2099-01-01";
  v2.hash = "synthetic".padEnd(64, "0");

  const d = v2.data;
  // Mutations chosen to hit each diff branch: text change, list growth,
  // pillar addition, pillar removal, task progress, and a brand-new change.
  d.pillars[0].tagline = "A deliberately altered tagline for the diff test.";
  d.pillars[0].gaps.push("A synthetic extra gap.");
  d.pillars[0].flow.push({ index: 99, title: "Synthetic step", detail: "<p>Added.</p>", files: [] });
  const dropped = d.pillars.pop();
  d.pillars.push({
    id: "synthetic-pillar",
    title: "Synthetic Pillar",
    order: 98,
    capabilities: [],
    status: "planned",
    tagline: "Exists only in the synthetic version.",
    what: "<p>New.</p>",
    why: "",
    flow: [{ index: 1, title: "Only step", detail: "<p>Detail.</p>", files: ["a/b.py"] }],
    facts: ["A fact."],
    gaps: ["A gap."],
    services: [],
    stores: [],
    changes: [],
    change_count: 0,
    shipped_change_count: 0,
    requirement_count: 0,
    scenario_count: 0
  });

  if (d.changes.length) {
    d.changes[0].tasks_done = Math.min(d.changes[0].tasks_total, d.changes[0].tasks_done + 5);
    d.changes[0].status = "in-flight";
    const fresh = JSON.parse(JSON.stringify(d.changes[0]));
    fresh.name = "synthetic-new-change";
    fresh.date = "2099-01-01";
    fresh.status = "shipped";
    fresh.archived = true;
    d.changes.unshift(fresh);
  }

  d.stats.pillars = d.pillars.length;
  d.stats.tasks_done += 5;
  d.stats.known_gaps += 2;
  d.stats.changes_total += 1;
  d.stats.changes_shipped += 1;
  d.stats.flow_steps += 2;

  v2.summary = {
    pillars: d.stats.pillars,
    changes_shipped: d.stats.changes_shipped,
    changes_total: d.stats.changes_total,
    tasks_done: d.stats.tasks_done,
    tasks_total: d.stats.tasks_total,
    known_gaps: d.stats.known_gaps
  };

  clone.versions.push(v2);
  return { payload: clone, droppedTitle: dropped.title };
}

const synth = syntheticTwoVersion(realPayload);
const synthRenders = exercise("synthetic", synth.payload);

// The diff must actually name what it found, not just render without throwing.
attempt("synthetic diff content", () => {
  const h = makeHarness(synth.payload);
  const seqs = synth.payload.versions.map((v) => v.seq);
  h.versionSelect.value = String(seqs[1]);
  h.fireChange(h.versionSelect);
  h.compareSelect.value = String(seqs[0]);
  h.fireChange(h.compareSelect);
  const markup = h.view.innerHTML;
  if (markup.indexOf("Pillars added") === -1) throw new Error("did not report the added pillar");
  if (markup.indexOf("Pillars removed") === -1) throw new Error("did not report the removed pillar");
  if (markup.indexOf(synth.droppedTitle) === -1) {
    throw new Error("removed pillar " + synth.droppedTitle + " not named");
  }
  if (markup.indexOf("synthetic-new-change") === -1) throw new Error("new spec change not reported");
  if (markup.indexOf("progressed") === -1) throw new Error("task progress not reported");
  if (markup.indexOf("Synthetic step") === -1) throw new Error("added flow step not shown in line diff");
});

if (failures.length) {
  failures.forEach((f) => console.error("FAIL " + f));
  console.error("\n" + failures.length + " failure(s)");
  process.exit(1);
}

console.log(
  "explainer smoke ok — real build: " +
    realPayload.versions.length +
    " version(s), " +
    realRenders.routes +
    " routes, " +
    realRenders.renders +
    " renders | synthetic 2-version diff: " +
    synthRenders.routes +
    " routes, " +
    synthRenders.renders +
    " renders | no exceptions"
);
