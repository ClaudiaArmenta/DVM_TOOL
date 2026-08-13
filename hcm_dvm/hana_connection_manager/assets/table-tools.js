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

  document.addEventListener("click", function (e) {
    if (!e.target.closest) return;
    var copyBtn = e.target.closest("[data-table-copy]");
    var expBtn = e.target.closest("[data-table-export]");
    var btn = copyBtn || expBtn;
    if (!btn) return;
    var table = tableFor(btn);
    if (!table) return;
    e.preventDefault();
    var m = matrix(table);
    if (!m.length) { flash(btn, false); return; }

    if (copyBtn) {
      copyText(toTSV(m)).then(function () { flash(btn, true); },
                             function () { flash(btn, false); });
    } else {
      var base = (btn.getAttribute("data-table-name") || "table")
        .replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "") || "table";
      download(base + ".csv", toCSV(m), "text/csv");
      flash(btn, true);
    }
  });
})();
