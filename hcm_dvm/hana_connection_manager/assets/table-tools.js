/* ─────────────────────────────────────────────────────────────────────────
   DVM Tool — per-table Copy / CSV export (client-side).

   Every table rendered by components.results_table() carries a small toolbar
   with a Copy and a CSV button (data-table-copy / data-table-export). This
   script serializes ONLY that table's visible rows — the one being shown —
   to TSV (clipboard) or CSV (download). Works for online and offline results
   alike; no server round-trip. Copying the displayed grid is exactly the
   "raw data as shown" the offline flow needs for paste-into-elsewhere.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  function matrix(table) {
    var rows = [];
    table.querySelectorAll("thead tr, tbody tr").forEach(function (tr) {
      if (tr.style.display === "none") return;   // respect the "top N" filter
      var cells = [];
      tr.querySelectorAll("th, td").forEach(function (c) {
        cells.push((c.innerText || c.textContent || "").trim());
      });
      if (cells.length) rows.push(cells);
    });
    return rows;
  }

  function toTSV(m) {
    return m.map(function (r) {
      return r.map(function (v) { return v.replace(/\t/g, " ").replace(/\r?\n/g, " "); }).join("\t");
    }).join("\n");
  }

  function toCSV(m) {
    return m.map(function (r) {
      return r.map(function (v) {
        return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
      }).join(",");
    }).join("\n");
  }

  function tableFor(btn) {
    var cont = btn.closest(".dvm-table-container");
    return cont ? cont.querySelector("table.dvm-table") : null;
  }

  function flash(btn, ok) {
    var i = btn.querySelector("i");
    if (!i) return;
    var prev = i.className;
    i.className = ok ? "bi bi-check-lg" : "bi bi-exclamation-triangle";
    btn.classList.add(ok ? "is-ok" : "is-err");
    setTimeout(function () {
      i.className = prev;
      btn.classList.remove("is-ok", "is-err");
    }, 1200);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (res, rej) {
      try {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        res();
      } catch (e) { rej(e); }
    });
  }

  // Build an Excel-openable file (HTML-table .xls) from the shown table.
  function toXLS(table, sheet) {
    var head = '<html xmlns:o="urn:schemas-microsoft-com:office:office" ' +
      'xmlns:x="urn:schemas-microsoft-com:office:excel" ' +
      'xmlns="http://www.w3.org/TR/REC-html40"><head><meta charset="utf-8">' +
      '<!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets>' +
      '<x:ExcelWorksheet><x:Name>' + (sheet || "Table").slice(0, 31) +
      '</x:Name><x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions>' +
      '</x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]-->' +
      '<style>td,th{border:1px solid #ccc;padding:4px;} th{background:#eee;font-weight:bold;}</style>' +
      '</head><body>';
    return head + table.outerHTML + "</body></html>";
  }

  function download(name, text, mime) {
    var blob = new Blob(["﻿" + text], { type: mime + ";charset=utf-8;" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 120);
  }

  // "Show top N" pills: show only the first N tbody rows of the sibling table.
  function applyTopN(wrap) {
    var active = wrap.querySelector("[data-toprows].active") || wrap.querySelector("[data-toprows]");
    if (!active) return;
    var n = parseInt(active.getAttribute("data-toprows"), 10) || 0;
    var table = wrap.querySelector("table.dvm-table");
    if (!table) return;
    var rows = table.querySelectorAll("tbody tr");
    for (var i = 0; i < rows.length; i++) rows[i].style.display = (i < n) ? "" : "none";
  }
  function applyAllTopN(root) {
    (root || document).querySelectorAll(".dvm-topn-wrap").forEach(applyTopN);
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("[data-toprows]") : null;
    if (!b) return;
    e.preventDefault();
    var wrap = b.closest(".dvm-topn-wrap");
    if (!wrap) return;
    wrap.querySelectorAll("[data-toprows]").forEach(function (x) {
      x.classList.toggle("active", x === b);
    });
    applyTopN(wrap);
  });
  // Apply the default (and re-apply to content Dash renders later).
  var topnObs = new MutationObserver(function () {
    if (topnObs._t) return;
    topnObs._t = setTimeout(function () { topnObs._t = null; applyAllTopN(document); }, 90);
  });
  function startTopN() {
    applyAllTopN(document);
    try { topnObs.observe(document.body, { childList: true, subtree: true }); } catch (e) {}
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", startTopN);
  else startTopN();

  document.addEventListener("click", function (e) {
    if (!e.target.closest) return;
    var copyBtn = e.target.closest("[data-table-copy]");
    var csvBtn = e.target.closest("[data-table-export]");
    var xlsBtn = e.target.closest("[data-table-export-xls]");
    var btn = copyBtn || csvBtn || xlsBtn;
    if (!btn) return;
    var table = tableFor(btn);
    if (!table) return;
    e.preventDefault();

    function fname(btn) {
      return (btn.getAttribute("data-table-name") || "table")
        .replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "") || "table";
    }

    if (copyBtn) {
      var m = matrix(table);
      if (!m.length) { flash(btn, false); return; }
      copyText(toTSV(m)).then(function () { flash(btn, true); },
                             function () { flash(btn, false); });
    } else if (csvBtn) {
      var mc = matrix(table);
      if (!mc.length) { flash(btn, false); return; }
      download(fname(btn) + ".csv", toCSV(mc), "text/csv");
      flash(btn, true);
    } else {
      download(fname(btn) + ".xls", toXLS(table, fname(btn)), "application/vnd.ms-excel");
      flash(btn, true);
    }
  });

  // Copy a card-style summary (e.g. A4 Top 10) as readable text.
  document.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("[data-copy-summary]") : null;
    if (!b) return;
    e.preventDefault();
    var cont = b.closest(".dvm-summary");
    if (!cont) return;
    var lines = [];
    cont.querySelectorAll("ol, ul").forEach(function (list) {
      var head = list.previousElementSibling;
      var title = head ? (head.innerText || head.textContent || "").trim() : "";
      if (title) lines.push(title);
      list.querySelectorAll("li").forEach(function (li) {
        lines.push("  " + (li.innerText || li.textContent || "").trim());
      });
      lines.push("");
    });
    var text = lines.join("\n").trim() || (cont.innerText || "").trim();
    copyText(text).then(function () { flash(b, true); }, function () { flash(b, false); });
  });
})();
