/* ─────────────────────────────────────────────────────────────────────────
   DVM Tool — help dialog + PDF (print) export.

   - Help button (#btn-help) opens a FAQ dialog (#help-backdrop); backdrop /
     close button / Escape close it. Pure client-side, no callbacks.
   - PDF button (#btn-export-pdf) triggers window.print(); a print stylesheet
     (assets/style.css @media print) hides the chrome and shows every analysis
     section so the browser's "Save as PDF" captures the full report.
   - The PDF button mirrors the visibility of "Export All" (#btn-export-excel),
     which the server reveals once analyses finish.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  function showHelp(on) {
    var m = document.getElementById("help-backdrop");
    if (m) m.style.display = on ? "grid" : "none";
  }

  document.addEventListener("click", function (e) {
    if (!e.target.closest) return;
    if (e.target.closest("#btn-help")) { e.preventDefault(); showHelp(true); return; }
    if (e.target.closest("[data-help-close]")) { e.preventDefault(); showHelp(false); return; }
    if (e.target.id === "help-backdrop") { showHelp(false); return; }
    if (e.target.closest("#btn-export-pdf")) { e.preventDefault(); window.print(); return; }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") showHelp(false);
  });

  // Charts mount inside hidden (display:none) sections and lay out at 0x0.
  // When a section becomes visible (sidebar / nav / "view details"), nudge a
  // resize so responsive Plotly graphs size themselves correctly.
  function nudgeCharts() {
    try { window.dispatchEvent(new Event("resize")); } catch (e) {}
    if (window.Plotly && window.Plotly.Plots) {
      document.querySelectorAll(".js-plotly-plot").forEach(function (gd) {
        if (gd.offsetParent !== null) { try { window.Plotly.Plots.resize(gd); } catch (e) {} }
      });
    }
  }
  document.addEventListener("click", function (e) {
    if (!e.target.closest) return;
    if (e.target.closest(".dvm-sidebar-item") || e.target.closest(".dvm-nav-tab")
        || e.target.closest("[id^='btn-goto-']")) {
      setTimeout(nudgeCharts, 130);
      setTimeout(nudgeCharts, 450);
    }
  });

  // Nudge whenever a section's visibility (inline style) changes...
  var secObs = new MutationObserver(function () { setTimeout(nudgeCharts, 70); });
  // ...and whenever results are (re)rendered into the content areas.
  var contentObs = new MutationObserver(function () {
    if (contentObs._t) return;
    contentObs._t = setTimeout(function () { contentObs._t = null; nudgeCharts(); }, 250);
  });
  function watchSections(tries) {
    var secs = document.querySelectorAll("[id^='section-'], #screen-analyses, #screen-offline");
    var panels = document.querySelectorAll("#analyses-content-panel, #offline-results-display");
    if (!secs.length && !panels.length) {
      if ((tries || 0) < 20) setTimeout(function () { watchSections((tries || 0) + 1); }, 500);
      return;
    }
    secs.forEach(function (s) {
      try { secObs.observe(s, { attributes: true, attributeFilter: ["style"] }); } catch (e) {}
    });
    panels.forEach(function (p) {
      try { contentObs.observe(p, { childList: true, subtree: true }); } catch (e) {}
    });
  }

  // Show "Detecting…" in the header while the DB version is auto-detected.
  function maybeShowDetecting() {
    var badge = document.getElementById("header-conn-badge");
    var vtext = document.getElementById("header-version-text");
    if (!badge || !vtext) return;
    if (badge.classList.contains("connected")) {
      var t = (vtext.textContent || "").trim();
      if (t === "" || /^no version$/i.test(t)) vtext.textContent = "Detecting…";
    }
  }
  var connObs = new MutationObserver(maybeShowDetecting);
  function watchConnection(tries) {
    var badge = document.getElementById("header-conn-badge");
    if (!badge) {
      if ((tries || 0) < 20) setTimeout(function () { watchConnection((tries || 0) + 1); }, 500);
      return;
    }
    try { connObs.observe(badge, { attributes: true, attributeFilter: ["class"] }); } catch (e) {}
    maybeShowDetecting();
  }

  // Keep the PDF button visibility in sync with "Export All".
  function syncPdf() {
    var ex = document.getElementById("btn-export-excel");
    var pdf = document.getElementById("btn-export-pdf");
    if (!ex || !pdf) return;
    pdf.style.display = (getComputedStyle(ex).display !== "none") ? "inline-flex" : "none";
  }

  var obs = new MutationObserver(syncPdf);

  function start() {
    var ex = document.getElementById("btn-export-excel");
    if (ex) { try { obs.observe(ex, { attributes: true, attributeFilter: ["style"] }); } catch (e) {} }
    syncPdf();
    setTimeout(syncPdf, 600);
    watchSections(0);
    watchConnection(0);
    [400, 1200, 2500].forEach(function (d) { setTimeout(nudgeCharts, d); });
  }
  window.addEventListener("load", function () { setTimeout(nudgeCharts, 200); });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
