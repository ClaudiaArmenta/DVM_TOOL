/* ─────────────────────────────────────────────────────────────────────────
   DVM Tool — lightweight client-side i18n.

   Translates static UI "chrome" (header, landing/Overview, action buttons,
   sidebar analysis titles) without touching the Dash callback graph. Elements
   opt in via attributes:
     data-i18n="key"        → sets textContent
     data-i18n-title="key"  → sets title + aria-label
     data-i18n-ph="key"     → sets placeholder
   The language is persisted in localStorage ('dvm-lang'); a MutationObserver
   re-applies translations to content Dash renders after load. HANA data
   (table/column names, query results) is intentionally left untranslated.
   Default language: English.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  var DICT = {
    en: {
      "nav.analyses": "Analyses",
      "nav.offline": "Offline",
      "btn.connect": "Connect",

      "lang.label": "Language",
      "numfmt.label": "Numbers",

      "table.copy": "Copy",
      "table.csv": "CSV",
      "table.copyTitle": "Copy this table to clipboard",
      "table.csvTitle": "Download this table as CSV",

      "overview.title": "DVM Analyses",
      "overview.subtitle": "Run analyses individually or as a batch. Queries execute serially via a single DBACOCKPIT session.",
      "overview.selectLabel": "Select analyses to run or export:",
      "overview.stillRunning": "Analyses are still running. Please wait for completion.",

      "btn.runAll": "Run All",
      "btn.runSelected": "Run Selected",
      "btn.exportAll": "Export All",
      "btn.exportSelected": "Export Selected",
      "btn.exportPdf": "Export PDF",

      "table.excel": "Excel",
      "table.excelTitle": "Download this table as Excel",
      "table.showTop": "Show top:",

      "help.btn": "Help & FAQ",
      "help.heading": "Help & FAQ",
      "help.q1": "It doesn't connect via SAP GUI. What do I do?",
      "help.a1intro": "The tool drives DBACOCKPIT through SAP GUI Scripting, so scripting must be enabled:",
      "help.a1s1": "Open SAP GUI and log into your system first (keep the session open).",
      "help.a1s2": "Enable the scripting parameter on the server: sapgui/user_scripting = TRUE.",
      "help.a1s3": "In SAP GUI: Options → Accessibility & Scripting → Scripting → check 'Enable scripting' (turn off the notification prompts).",
      "help.a1s4": "Back here, click Detect Sessions / Connect.",
      "help.contact": "Suggestions? Email ",

      "offline.assign": "Assign uploads to (auto-detect, or pick one):",

      "sidebar.overview": "Overview",

      "howto.title": "How to use this tool",
      "howto.step1": "Select or detect the database.",
      "howto.step2": "Choose which analyses to run.",
      "howto.step3": "View the results or export.",
      "howto.disclaimer": "Some analyses run heavy SQL and can take a while. If a query seems slow, just give it time. Don't refresh. Results appear as each analysis finishes.",

      "info.a1": "Top tables by disk and memory size",
      "info.a2": "Memory & disk resource trend (~1 year, monthly)",
      "info.a3": "Memory distribution by subarea (pie chart)",
      "info.a4": "Top growing tables over last 30 days",
      "info.a5": "Partitioned column-store tables",

      "analysis.a1_top_tables.short": "Top Tables by Size",
      "analysis.a2_db_size_history.short": "DB Size & Memory History",
      "analysis.a3_memory_overview.short": "Memory Overview",
      "analysis.a4_top_growing.short": "Top Growing Tables (30d)",
      "analysis.a5_partitioned_tables.short": "Partitioned Tables",

      "analysis.a1_top_tables.desc": "Largest tables by disk and memory (SAP Note 1969700), enriched with table descriptions.",
      "analysis.a2_db_size_history.desc": "CPU and memory resource trend over ~1 year (SAP Note 1969700).",
      "analysis.a3_memory_overview.desc": "Memory resource consumption by subarea.",
      "analysis.a4_top_growing.desc": "Tables with highest growth in records, disk, and memory over 30 days.",
      "analysis.a5_partitioned_tables.desc": "Column-store partitioned tables overview."
    },

    es: {
      "nav.analyses": "Análisis",
      "nav.offline": "Sin conexión",
      "btn.connect": "Conectar",

      "lang.label": "Idioma",
      "numfmt.label": "Números",

      "table.copy": "Copiar",
      "table.csv": "CSV",
      "table.copyTitle": "Copiar esta tabla al portapapeles",
      "table.csvTitle": "Descargar esta tabla como CSV",

      "overview.title": "Análisis DVM",
      "overview.subtitle": "Ejecuta los análisis de forma individual o por lotes. Las consultas se ejecutan en serie mediante una única sesión de DBACOCKPIT.",
      "overview.selectLabel": "Selecciona los análisis a ejecutar o exportar:",
      "overview.stillRunning": "Los análisis siguen en ejecución. Espera a que terminen.",

      "btn.runAll": "Ejecutar todo",
      "btn.runSelected": "Ejecutar selección",
      "btn.exportAll": "Exportar todo",
      "btn.exportSelected": "Exportar selección",
      "btn.exportPdf": "Exportar PDF",

      "table.excel": "Excel",
      "table.excelTitle": "Descargar esta tabla como Excel",
      "table.showTop": "Mostrar top:",

      "help.btn": "Ayuda y FAQ",
      "help.heading": "Ayuda y preguntas frecuentes",
      "help.q1": "No conecta por SAP GUI, ¿qué hago?",
      "help.a1intro": "La herramienta usa DBACOCKPIT vía SAP GUI Scripting, así que el scripting debe estar habilitado:",
      "help.a1s1": "Abre SAP GUI e inicia sesión en tu sistema primero (deja la sesión abierta).",
      "help.a1s2": "Habilita el parámetro de scripting en el servidor: sapgui/user_scripting = TRUE.",
      "help.a1s3": "En SAP GUI: Opciones → Accesibilidad y scripting → Scripting → marca 'Habilitar scripting' (desactiva los avisos de notificación).",
      "help.a1s4": "Vuelve aquí y pulsa Detectar sesiones / Conectar.",
      "help.contact": "¿Sugerencias? Escribe a ",

      "offline.assign": "Asignar subidas a (autodetectar o elegir una):",

      "sidebar.overview": "Resumen",

      "howto.title": "Cómo usar esta herramienta",
      "howto.step1": "Selecciona o detecta la base de datos.",
      "howto.step2": "Escoge qué análisis ejecutar.",
      "howto.step3": "Ve los resultados o exporta.",
      "howto.disclaimer": "Algunos análisis ejecutan SQL pesado y pueden tardar. Si una consulta parece lenta, solo dale tiempo, no recargues. Los resultados aparecen conforme cada análisis termina.",

      "info.a1": "Tablas más grandes por disco y memoria",
      "info.a2": "Tendencia de memoria y disco (~1 año, mensual)",
      "info.a3": "Distribución de memoria por subárea (gráfico circular)",
      "info.a4": "Tablas de mayor crecimiento en los últimos 30 días",
      "info.a5": "Tablas particionadas en column-store",

      "analysis.a1_top_tables.short": "Tablas más grandes por tamaño",
      "analysis.a2_db_size_history.short": "Historial de tamaño de BD y memoria",
      "analysis.a3_memory_overview.short": "Resumen de memoria",
      "analysis.a4_top_growing.short": "Tablas de mayor crecimiento (30d)",
      "analysis.a5_partitioned_tables.short": "Tablas particionadas",

      "analysis.a1_top_tables.desc": "Tablas más grandes por disco y memoria (SAP Note 1969700), enriquecidas con descripciones de tablas.",
      "analysis.a2_db_size_history.desc": "Tendencia de recursos de CPU y memoria durante ~1 año (SAP Note 1969700).",
      "analysis.a3_memory_overview.desc": "Consumo de recursos de memoria por subárea.",
      "analysis.a4_top_growing.desc": "Tablas con mayor crecimiento en registros, disco y memoria en 30 días.",
      "analysis.a5_partitioned_tables.desc": "Resumen de tablas particionadas en column-store."
    },

    pt: {
      "nav.analyses": "Análises",
      "nav.offline": "Offline",
      "btn.connect": "Conectar",

      "lang.label": "Idioma",
      "numfmt.label": "Números",

      "table.copy": "Copiar",
      "table.csv": "CSV",
      "table.copyTitle": "Copiar esta tabela para a área de transferência",
      "table.csvTitle": "Baixar esta tabela como CSV",

      "overview.title": "Análises DVM",
      "overview.subtitle": "Execute as análises individualmente ou em lote. As consultas são executadas em série por meio de uma única sessão do DBACOCKPIT.",
      "overview.selectLabel": "Selecione as análises para executar ou exportar:",
      "overview.stillRunning": "As análises ainda estão em execução. Aguarde a conclusão.",

      "btn.runAll": "Executar tudo",
      "btn.runSelected": "Executar selecionados",
      "btn.exportAll": "Exportar tudo",
      "btn.exportSelected": "Exportar selecionados",
      "btn.exportPdf": "Exportar PDF",

      "table.excel": "Excel",
      "table.excelTitle": "Baixar esta tabela como Excel",
      "table.showTop": "Mostrar top:",

      "help.btn": "Ajuda e FAQ",
      "help.heading": "Ajuda e perguntas frequentes",
      "help.q1": "Não conecta via SAP GUI, o que faço?",
      "help.a1intro": "A ferramenta usa o DBACOCKPIT via SAP GUI Scripting, então o scripting precisa estar habilitado:",
      "help.a1s1": "Abra o SAP GUI e faça login no seu sistema primeiro (mantenha a sessão aberta).",
      "help.a1s2": "Habilite o parâmetro de scripting no servidor: sapgui/user_scripting = TRUE.",
      "help.a1s3": "No SAP GUI: Opções → Acessibilidade e scripting → Scripting → marque 'Habilitar scripting' (desative os avisos de notificação).",
      "help.a1s4": "Volte aqui e clique em Detectar sessões / Conectar.",
      "help.contact": "Sugestões? Envie e-mail para ",

      "offline.assign": "Atribuir uploads a (detecção automática ou escolher):",

      "sidebar.overview": "Visão geral",

      "howto.title": "Como usar esta ferramenta",
      "howto.step1": "Selecione ou detecte o banco de dados.",
      "howto.step2": "Escolha quais análises executar.",
      "howto.step3": "Veja os resultados ou exporte.",
      "howto.disclaimer": "Algumas análises executam SQL pesado e podem demorar. Se uma consulta parecer lenta, apenas aguarde, não atualize. Os resultados aparecem conforme cada análise termina.",

      "info.a1": "Maiores tabelas por disco e memória",
      "info.a2": "Tendência de memória e disco (~1 ano, mensal)",
      "info.a3": "Distribuição de memória por subárea (gráfico de pizza)",
      "info.a4": "Tabelas com maior crescimento nos últimos 30 dias",
      "info.a5": "Tabelas particionadas em column-store",

      "analysis.a1_top_tables.short": "Maiores tabelas por tamanho",
      "analysis.a2_db_size_history.short": "Histórico de tamanho do BD e memória",
      "analysis.a3_memory_overview.short": "Visão geral de memória",
      "analysis.a4_top_growing.short": "Tabelas com maior crescimento (30d)",
      "analysis.a5_partitioned_tables.short": "Tabelas particionadas",

      "analysis.a1_top_tables.desc": "Maiores tabelas por disco e memória (SAP Note 1969700), enriquecidas com descrições de tabelas.",
      "analysis.a2_db_size_history.desc": "Tendência de recursos de CPU e memória ao longo de ~1 ano (SAP Note 1969700).",
      "analysis.a3_memory_overview.desc": "Consumo de recursos de memória por subárea.",
      "analysis.a4_top_growing.desc": "Tabelas com maior crescimento em registros, disco e memória em 30 dias.",
      "analysis.a5_partitioned_tables.desc": "Visão geral de tabelas particionadas em column-store."
    }
  };

  var LS_KEY = "dvm-lang";

  function getLang() {
    try {
      var s = localStorage.getItem(LS_KEY);
      if (s && DICT[s]) return s;
    } catch (e) {}
    return "en";
  }

  function tr(lang, key) {
    if (DICT[lang] && DICT[lang][key] != null) return DICT[lang][key];
    if (DICT.en[key] != null) return DICT.en[key];
    return null;
  }

  function apply(root) {
    var lang = getLang();
    var scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach(function (el) {
      var v = tr(lang, el.getAttribute("data-i18n"));
      if (v != null && el.textContent !== v) el.textContent = v;
    });
    scope.querySelectorAll("[data-i18n-title]").forEach(function (el) {
      var v = tr(lang, el.getAttribute("data-i18n-title"));
      if (v != null) { el.setAttribute("title", v); el.setAttribute("aria-label", v); }
    });
    scope.querySelectorAll("[data-i18n-ph]").forEach(function (el) {
      var v = tr(lang, el.getAttribute("data-i18n-ph"));
      if (v != null) el.setAttribute("placeholder", v);
    });
    document.documentElement.setAttribute("lang", lang);
    document.querySelectorAll("[data-lang]").forEach(function (b) {
      var on = b.getAttribute("data-lang") === lang;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function setLang(lang) {
    if (!DICT[lang]) return;
    try { localStorage.setItem(LS_KEY, lang); } catch (e) {}
    apply(document);
  }

  // Expose for debugging / future server hooks.
  window.__dvmSetLang = setLang;
  window.__dvmApplyI18n = apply;
  window.__dvmGetLang = getLang;

  // Language selector clicks (delegated — survives Dash re-renders).
  document.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("[data-lang]") : null;
    if (!b) return;
    e.preventDefault();
    setLang(b.getAttribute("data-lang"));
  });

  // Re-apply to content Dash renders after load (debounced).
  var observer = new MutationObserver(function () {
    if (observer._t) return;
    observer._t = setTimeout(function () { observer._t = null; apply(document); }, 60);
  });

  function start() {
    apply(document);
    try { observer.observe(document.body, { childList: true, subtree: true }); } catch (e) {}
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
