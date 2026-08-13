/* ─────────────────────────────────────────────────────────────────────────
   DVM Tool — number-format toggle (US 1,000.00  ↔  EU 1.000,00).

   The server always emits US-formatted numbers. This script captures each
   numeric element's value once (storing the canonical number + its decimal
   count + any prefix/suffix like " GB"), then rewrites the displayed text to
   the chosen format. Choice persists in localStorage ('dvm-numfmt'); a
   MutationObserver reformats content Dash renders later. Charts (Plotly) keep
   US formatting — only DOM text is localized. Default: US.

   Targets: numeric table cells (td.dvm-table-num), KPI values (.metric-value,
   .dvm-metric-value) and anything tagged .dvm-num (e.g. the Situation box).
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  var LS = "dvm-numfmt";
  var SEL = "td.dvm-table-num, .metric-value, .dvm-metric-value, .dvm-num";

  function get() {
    try { var v = localStorage.getItem(LS); if (v === "eu" || v === "us") return v; } catch (e) {}
    return "us";
  }

  // Capture a US-formatted number from an element's text (run once per element).
  function capture(el) {
    var raw = el.textContent;
    var m = raw.match(/-?\d[\d,]*(?:\.\d+)?/);   // US: comma thousands, dot decimal
    if (!m) { el.setAttribute("data-num", "NaN"); return; }
    var numStr = m[0];
    var num = parseFloat(numStr.replace(/,/g, ""));
    if (isNaN(num)) { el.setAttribute("data-num", "NaN"); return; }
    var dot = numStr.indexOf(".");
    var dec = dot < 0 ? 0 : (numStr.length - dot - 1);
    el.setAttribute("data-num", String(num));
    el.setAttribute("data-num-dec", String(dec));
    el.setAttribute("data-num-pre", raw.slice(0, m.index));
    el.setAttribute("data-num-suf", raw.slice(m.index + m[0].length));
  }

  function format(num, dec, mode) {
    var neg = num < 0;
    var parts = Math.abs(num).toFixed(dec).split(".");
    var thou = mode === "eu" ? "." : ",";
    var deci = mode === "eu" ? "," : ".";
    var intp = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, thou);
    return (neg ? "-" : "") + intp + (parts[1] ? deci + parts[1] : "");
  }

  function apply(root) {
    var mode = get();
    (root || document).querySelectorAll(SEL).forEach(function (el) {
      if (!el.hasAttribute("data-num")) capture(el);
      var canon = el.getAttribute("data-num");
      if (canon === "NaN") return;
      var dec = parseInt(el.getAttribute("data-num-dec") || "0", 10);
      var pre = el.getAttribute("data-num-pre") || "";
      var suf = el.getAttribute("data-num-suf") || "";
      el.textContent = pre + format(parseFloat(canon), dec, mode) + suf;
    });
    document.querySelectorAll("[data-numfmt]").forEach(function (b) {
      var on = b.getAttribute("data-numfmt") === mode;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function set(mode) {
    if (mode !== "us" && mode !== "eu") return;
    try { localStorage.setItem(LS, mode); } catch (e) {}
    apply(document);
  }

  window.__dvmSetNumFmt = set;
  window.__dvmApplyNumFmt = apply;

  document.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("[data-numfmt]") : null;
    if (!b) return;
    e.preventDefault();
    set(b.getAttribute("data-numfmt"));
  });

  var obs = new MutationObserver(function () {
    if (obs._t) return;
    obs._t = setTimeout(function () { obs._t = null; apply(document); }, 60);
  });

  function start() {
    apply(document);
    try { obs.observe(document.body, { childList: true, subtree: true }); } catch (e) {}
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
