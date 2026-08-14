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
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
