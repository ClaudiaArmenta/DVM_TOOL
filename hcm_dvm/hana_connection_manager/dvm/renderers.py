"""Renderers for DVM analyses.

Each renderer takes a list of result dicts (one per query) and returns a Dash
component tree. Charts use Plotly with a consistent DVM theme.
"""

from typing import Dict, List, Optional

import pandas as pd
from dash import html, dcc
import dash_bootstrap_components as dbc

from .components import results_table, status_badge, elapsed_badge, row_col_badge, collapsible_sql


# ═══════════════════════════════════════════════════════════════════════════
# PLOTLY THEME (consistent across all charts)
# ═══════════════════════════════════════════════════════════════════════════

# Organic categorical series palette (mirrors --series-1…8 in assets/style.css),
# padded to 10 with two deeper ramp steps.
_CHART_COLORS = ["#0070f2", "#b8541a", "#2f7d6a", "#7b5ea7", "#a3123a",
                 "#5b738b", "#b08a1e", "#3f7a2e", "#0d3673", "#8b4a0b"]

_CHART_LAYOUT = dict(
    font=dict(family="Figtree, system-ui, -apple-system, sans-serif", size=12, color="#556B82"),
    plot_bgcolor="white",
    paper_bgcolor="white",
    margin=dict(l=50, r=20, t=40, b=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                font=dict(size=11)),
    xaxis=dict(gridcolor="#E5E7EB", gridwidth=1, zeroline=False,
               title_font=dict(size=12, color="#556B82")),
    yaxis=dict(gridcolor="#E5E7EB", gridwidth=1, zeroline=False,
               title_font=dict(size=12, color="#556B82")),
)


def _chart_card(fig, title: str = "") -> html.Div:
    """Wrap a Plotly figure in a styled chart card."""
    children = []
    if title:
        children.append(
            html.Div(title, style={"fontSize": "14px", "fontWeight": "600",
                                   "color": "#1D2D3E", "marginBottom": "8px"})
        )
    children.append(dcc.Graph(figure=fig, config={"displayModeBar": False},
                              style={"borderRadius": "6px"}))
    return html.Div(children, className="dvm-chart-card")


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _source_badge(source_label: str) -> html.Span:
    """Render a source label badge."""
    cls = "dvm-badge dvm-badge-info"
    if "SQL Statement Collection" in source_label:
        cls = "dvm-badge dvm-badge-info"
    elif "authored" in source_label:
        cls = "dvm-badge dvm-badge-neutral"
    elif "error" in source_label or "stub" in source_label:
        cls = "dvm-badge dvm-badge-warning"
    return html.Span(source_label, className=cls)


def _section_header(title: str, source_label: str, elapsed_ms: float = 0,
                    rows: int = 0, cols: int = 0) -> html.Div:
    """Render a section header with source badge and stats."""
    badges = [_source_badge(source_label)]
    if elapsed_ms > 0:
        badges.append(elapsed_badge(elapsed_ms))
    if rows > 0:
        badges.append(row_col_badge(rows, cols))
    return html.Div(
        [
            html.H3(title, style={"margin": "0", "fontWeight": "600", "fontSize": "15px",
                                  "color": "#1D2D3E"}),
            html.Div(badges, style={"display": "flex", "alignItems": "center",
                                    "gap": "6px", "flexWrap": "wrap"}),
        ],
        style={"display": "flex", "justifyContent": "space-between",
               "alignItems": "center", "marginBottom": "10px", "marginTop": "20px"},
    )


def _enrich_a1_df(df: pd.DataFrame, enrichment_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Join enrichment data (DDTEXT, partitioning) onto A1 results."""
    if enrichment_df is None or enrichment_df.empty:
        return df
    if df is None or df.empty:
        return df

    df_cols = [c.upper().strip() for c in df.columns]
    df.columns = df_cols
    enrich_cols = [c.upper().strip() for c in enrichment_df.columns]
    enrichment_df.columns = enrich_cols

    join_keys = []
    if "SCHEMA_NAME" in df.columns and "SCHEMA_NAME" in enrichment_df.columns:
        join_keys.append("SCHEMA_NAME")
    if "TABLE_NAME" in df.columns and "TABLE_NAME" in enrichment_df.columns:
        join_keys.append("TABLE_NAME")

    if not join_keys:
        return df

    enrich_add_cols = ["DDTEXT", "PARTITIONING", "PART_COUNT"]
    available = [c for c in enrich_add_cols if c in enrichment_df.columns and c not in df.columns]

    if not available:
        if "DDTEXT" in enrichment_df.columns:
            available = ["DDTEXT"]
        else:
            return df

    merge_cols = join_keys + available
    enrich_subset = enrichment_df[merge_cols].drop_duplicates(subset=join_keys)

    try:
        result = df.merge(enrich_subset, on=join_keys, how="left")
        if "DDTEXT" in result.columns:
            cols = list(result.columns)
            cols.remove("DDTEXT")
            tn_idx = cols.index("TABLE_NAME") + 1 if "TABLE_NAME" in cols else 0
            cols.insert(tn_idx, "DDTEXT")
            result = result[cols]
        return result
    except Exception:
        return df


# ═══════════════════════════════════════════════════════════════════════════
# RENDERERS
# ═══════════════════════════════════════════════════════════════════════════

def render_a1(results: List[dict], revision: str) -> html.Div:
    """Render A1 -- Top Tables (overview table + two detail tables: by disk, by memory)."""
    children = []

    # Build overview combining both queries if available
    overview_dfs = []
    for res in results:
        if res.get("success") and res.get("df") is not None:
            enrichment_df = res.get("enrichment_df")
            rdf = res["df"].copy()
            if enrichment_df is not None:
                rdf = _enrich_a1_df(rdf, enrichment_df)
            overview_dfs.append(rdf)

    if overview_dfs:
        children.append(_build_a1_overview(overview_dfs))

    # Detail tables
    labels = ["Top Tables by Disk Size", "Top Tables by Memory Size"]
    for i, res in enumerate(results):
        label = labels[i] if i < len(labels) else f"Result {i+1}"
        src = res.get("source_label", f"generated (rev {revision})")
        children.append(_section_header(label, src,
                                        elapsed_ms=res.get("elapsed_ms", 0),
                                        rows=res.get("row_count", 0),
                                        cols=res.get("col_count", 0)))
        if res.get("success"):
            df = res.get("df")
            enrichment_df = res.get("enrichment_df")
            if df is not None and enrichment_df is not None:
                df = _enrich_a1_df(df, enrichment_df)
            children.append(results_table(df, max_rows=100))
            children.append(collapsible_sql(res.get("sql", "")))
        else:
            children.append(html.Div(
                [html.I(className="bi bi-exclamation-triangle me-2"),
                 html.Span(res.get("error", "Unknown error"))],
                className="dvm-error-card",
            ))
    return html.Div(children)


def _build_a1_overview(dfs: List[pd.DataFrame]) -> html.Div:
    """Build a combined overview showing top tables by Memory first, then Disk."""
    sections = []

    # Determine if we have memory and disk separately
    # First DF = disk, Second DF = memory (from registry order)
    disk_df = dfs[0] if len(dfs) > 0 else None
    mem_df = dfs[1] if len(dfs) > 1 else disk_df

    def _extract_overview(df, sort_col_hint, label):
        """Extract overview columns: Table Name, Memory GB, Disk GB, Description, App Area."""
        if df is None or df.empty:
            return None
        odf = df.copy()
        odf.columns = [c.upper().strip() for c in odf.columns]

        # Find key columns
        table_col = next((c for c in odf.columns if c == "TABLE_NAME"), None)
        schema_col = next((c for c in odf.columns if c == "SCHEMA_NAME"), None)
        mem_col = None
        disk_col = None
        desc_col = None
        app_col = None

        for c in odf.columns:
            if "MEM" in c and "GB" in c and not mem_col:
                mem_col = c
            elif "DISK" in c and "GB" in c and not disk_col:
                disk_col = c
            elif c == "DDTEXT" and not desc_col:
                desc_col = c
            elif ("APP" in c or "COMPONENT" in c) and not app_col:
                app_col = c

        if not table_col:
            return None

        # Build overview DF
        cols_out = []
        renames = {}
        if schema_col:
            cols_out.append(schema_col)
            renames[schema_col] = "Schema"
        cols_out.append(table_col)
        renames[table_col] = "Table Name"
        if mem_col:
            cols_out.append(mem_col)
            renames[mem_col] = "Memory Size (GB)"
        if disk_col:
            cols_out.append(disk_col)
            renames[disk_col] = "Disk Size (GB)"
        if desc_col:
            cols_out.append(desc_col)
            renames[desc_col] = "Description"
        if app_col:
            cols_out.append(app_col)
            renames[app_col] = "Application Area"

        available = [c for c in cols_out if c in odf.columns]
        result = odf[available].head(10).copy()
        result = result.rename(columns={k: v for k, v in renames.items() if k in result.columns})
        return result

    # Memory overview first
    mem_overview = _extract_overview(mem_df, "MEM", "Memory")
    if mem_overview is not None and not mem_overview.empty:
        sections.append(
            html.Div([
                html.H4("Top 10 Tables by Memory",
                         style={"fontSize": "14px", "fontWeight": "600",
                                "color": "#1D2D3E", "marginBottom": "8px"}),
                results_table(mem_overview, max_rows=10),
            ], style={"marginBottom": "20px"})
        )

    # Disk overview second
    disk_overview = _extract_overview(disk_df, "DISK", "Disk")
    if disk_overview is not None and not disk_overview.empty:
        sections.append(
            html.Div([
                html.H4("Top 10 Tables by Disk",
                         style={"fontSize": "14px", "fontWeight": "600",
                                "color": "#1D2D3E", "marginBottom": "8px"}),
                results_table(disk_overview, max_rows=10),
            ], style={"marginBottom": "20px"})
        )

    if not sections:
        return html.Div()

    return html.Div(
        [
            html.Div(
                [html.I(className="bi bi-clipboard-data me-2",
                        style={"color": "var(--dvm-primary)"}),
                 html.Span("Top Tables Overview", style={"fontWeight": "600", "fontSize": "14px"})],
                style={"marginBottom": "12px"},
            ),
            *sections,
            html.Hr(style={"margin": "24px 0", "borderColor": "var(--dvm-border)"}),
        ],
    )


def _to_num(series):
    """Coerce a column to numeric, tolerating US ('1,234.56') and European
    ('1.234,56') thousands/decimal formats plus unit suffixes like 'GB'."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    s = series.astype(str).str.strip().str.replace(r"[^\d.,\-]", "", regex=True)

    def conv(v):
        if not v or v in ("-", ".", ","):
            return float("nan")
        last_dot, last_comma = v.rfind("."), v.rfind(",")
        if last_comma > last_dot:            # comma is the decimal sep (EU)
            v = v.replace(".", "").replace(",", ".")
        else:                                 # dot is decimal (US) — drop comma thousands
            v = v.replace(",", "")
        try:
            return float(v)
        except ValueError:
            return float("nan")

    return s.map(conv)


def _build_situation_box(chart_df, ts_col, disk_size_col, total_mem_col,
                         cs_col, rs_col) -> html.Div:
    """'Situation as of <date>' snapshot: disk size, total memory, and its
    column-/row-store split — whichever of those columns are present."""
    def latest(col):
        if not col or col not in chart_df.columns:
            return None
        vals = _to_num(chart_df[col]).dropna()
        return float(vals.iloc[-1]) if len(vals) else None

    disk = latest(disk_size_col)
    total_mem = latest(total_mem_col)
    cs = latest(cs_col)
    rs = latest(rs_col)

    if disk is None and total_mem is None and cs is None and rs is None:
        return html.Div()

    # Situation date = latest snapshot in the data, else now.
    when = None
    if ts_col and ts_col in chart_df.columns:
        dts = pd.to_datetime(chart_df[ts_col], errors="coerce").dropna()
        if len(dts):
            when = dts.max()
    if when is None:
        when = pd.Timestamp.now()
    date_str = f"{when:%B} {when.day}, {when.year}"

    def line(label, val, indent=False):
        return html.Div(
            [
                html.Span(label, style={"color": "var(--dvm-text-secondary)",
                                        "marginRight": "8px"}),
                html.Span(f"{val:,.2f} GB", className="dvm-num",
                          style={"fontWeight": "600",
                                 "fontVariantNumeric": "tabular-nums"}),
            ],
            style={"fontSize": "13px", "padding": "3px 0",
                   "paddingLeft": ("22px" if indent else "0")},
        )

    rows = []
    if disk is not None:
        rows.append(line("Disk Size:", disk))
    if total_mem is not None:
        rows.append(line("Total Memory Size:", total_mem))
    if cs is not None:
        rows.append(line("Column Store Size:", cs, indent=True))
    if rs is not None:
        rows.append(line("Row Store Size:", rs, indent=True))

    return html.Div(
        [
            html.Div(
                [html.I(className="bi bi-clipboard-pulse me-2",
                        style={"color": "var(--dvm-primary)"}),
                 html.Span(f"Situation as of {date_str}",
                           style={"fontWeight": "600", "fontSize": "13px"})],
                style={"marginBottom": "8px"},
            ),
            html.Div(rows),
        ],
        className="dvm-info-card",
        style={"marginBottom": "16px", "padding": "12px 16px",
               "flexDirection": "column", "alignItems": "stretch"},
    )


def render_a2(results: List[dict], revision: str) -> html.Div:
    """Render A2 -- DB Size & Memory History with monthly line chart and Situation box."""
    children = []
    if not results:
        return html.Div("No results.")

    res = results[0]
    children.append(_section_header(
        "Memory & Resource History (~1 Year)",
        res.get("source_label", f"generated (rev {revision})"),
        elapsed_ms=res.get("elapsed_ms", 0),
        rows=res.get("row_count", 0),
        cols=res.get("col_count", 0),
    ))

    if not res.get("success"):
        children.append(html.Div(
            [html.I(className="bi bi-x-circle me-2"),
             html.Span(res.get("error", ""))],
            className="dvm-error-card",
        ))
        return html.Div(children)

    df = res.get("df")
    if df is None or df.empty:
        children.append(html.Div(
            [html.I(className="bi bi-bar-chart",
                    style={"fontSize": "20px", "color": "var(--dvm-border)"}),
             html.P("No history data in the requested time range.")],
            className="dvm-empty-state",
        ))
        return html.Div(children)

    try:
        import plotly.graph_objects as go

        chart_df = df.copy()
        chart_df.columns = [c.upper().strip() for c in chart_df.columns]
        cols = list(chart_df.columns)

        def find(pred):
            return next((c for c in cols if pred(c)), None)

        # ── Month key: prefer explicit YEAR + MONTH, else a date/timestamp ──
        year_col = find(lambda c: c in ("YEAR", "YR"))
        month_col = find(lambda c: c in ("MONTH", "MON", "MTH", "MONTH_NO"))
        day_col = find(lambda c: c in ("DAY", "DAY_NO"))
        ts_col = (find(lambda c: "SNAPSHOT" in c or "TIMESTAMP" in c)
                  or find(lambda c: c in ("TIME", "DATE", "DATETIME", "DATE_TIME"))
                  or find(lambda c: "DATE" in c or "TIME" in c))

        if year_col and month_col:
            yy = pd.to_numeric(chart_df[year_col], errors="coerce")
            mm = pd.to_numeric(chart_df[month_col], errors="coerce")
            dd = (pd.to_numeric(chart_df[day_col], errors="coerce")
                  if day_col else pd.Series(1, index=chart_df.index))
            chart_df["_TS"] = pd.to_datetime(
                dict(year=yy, month=mm, day=dd), errors="coerce")
        elif ts_col:
            chart_df["_TS"] = pd.to_datetime(chart_df[ts_col], errors="coerce", dayfirst=True)
        else:
            chart_df["_TS"] = pd.NaT

        has_time = chart_df["_TS"].notna().any()
        if has_time:
            chart_df = chart_df.dropna(subset=["_TS"]).sort_values("_TS")

        # ── Value columns for the monthly trend chart ──
        used_col = (find(lambda c: "HANA_USED" in c and "GB" in c)
                    or find(lambda c: ("MEMORY" in c or "MEM" in c)
                            and "USED" in c and "GB" in c))
        disk_used_col = (find(lambda c: "DISK" in c and "USED" in c and "GB" in c)
                         or find(lambda c: c == "DISK_USED_GB")
                         or find(lambda c: "DATA_DISK" in c and "GB" in c))
        alloc_col = (find(lambda c: "ALLOC_LIM" in c and "GB" in c)
                     or find(lambda c: "HANA_ALLOC" in c and "GB" in c))

        # ── Current-snapshot columns for the Situation box ──
        disk_size_col = (find(lambda c: "DISK" in c and "SIZE" in c and "GB" in c)
                         or find(lambda c: "DISK" in c and "TOTAL" in c and "GB" in c)
                         or disk_used_col)
        total_mem_col = (find(lambda c: "TOTAL" in c and ("MEMORY" in c or "MEM" in c) and "GB" in c)
                         or find(lambda c: ("MEMORY" in c or "MEM" in c) and "SIZE" in c and "GB" in c)
                         or used_col)
        cs_col = (find(lambda c: "COLUMN" in c and "STORE" in c)
                  or find(lambda c: c.startswith("CS_") and "GB" in c)
                  or find(lambda c: "COLUMN_STORE" in c))
        rs_col = (find(lambda c: "ROW" in c and "STORE" in c)
                  or find(lambda c: c.startswith("RS_") and "GB" in c)
                  or find(lambda c: "ROW_STORE" in c))

        # Situation summary box (current snapshot)
        children.append(_build_situation_box(
            chart_df, "_TS" if has_time else None,
            disk_size_col, total_mem_col, cs_col, rs_col))

        if not has_time or (not used_col and not disk_used_col and not alloc_col):
            children.append(html.Div(
                "Trend chart unavailable: need a date (or Year + Month) column and "
                "at least one of Memory Used (GB) / Disk Used Data (GB).",
                className="dvm-warning-card",
            ))
        else:
            # Group by month and average within each month
            monthly = chart_df.copy()
            monthly["_MONTH"] = monthly["_TS"].dt.to_period("M")

            agg_cols = {}
            for c in (used_col, disk_used_col, alloc_col):
                if c:
                    monthly[c] = _to_num(monthly[c])
                    agg_cols[c] = "mean"

            monthly_agg = monthly.groupby("_MONTH", as_index=False).agg(agg_cols)
            monthly_agg["_DATE"] = monthly_agg["_MONTH"].apply(lambda p: p.to_timestamp())
            x_vals = monthly_agg["_DATE"]

            fig = go.Figure()
            if used_col:
                fig.add_trace(go.Scatter(
                    x=x_vals, y=monthly_agg[used_col],
                    mode="lines+markers", name="Memory Used (GB)",
                    line=dict(color=_CHART_COLORS[0], width=2.5),
                    marker=dict(size=5),
                ))
            if disk_used_col:
                fig.add_trace(go.Scatter(
                    x=x_vals, y=monthly_agg[disk_used_col],
                    mode="lines+markers", name="Disk Used Data (GB)",
                    line=dict(color=_CHART_COLORS[2], width=2.5),
                    marker=dict(size=5),
                ))
            if alloc_col:
                fig.add_trace(go.Scatter(
                    x=x_vals, y=monthly_agg[alloc_col],
                    mode="lines", name="Allocation Limit (GB)",
                    line=dict(color=_CHART_COLORS[1], width=2, dash="dot"),
                ))

            fig.update_layout(height=380, yaxis_title="GB", **_CHART_LAYOUT)
            fig.update_layout(
                title=dict(text="Monthly Resource Trend", font=dict(size=14)),
                xaxis=dict(tickformat="%b %Y"),
            )
            children.append(_chart_card(fig))

    except ImportError:
        children.append(html.Div("Plotly not installed.", className="dvm-warning-card"))
    except Exception as e:
        children.append(html.Div(f"Chart error: {e}", className="dvm-error-card"))

    children.append(collapsible_sql(res.get("sql", "")))
    children.append(results_table(df, max_rows=200, name="Memory_History"))
    return html.Div(children)


def render_a3(results: List[dict], revision: str) -> html.Div:
    """Render A3 -- Memory Overview (pie chart by SUBAREA + table)."""
    children = []
    if not results:
        return html.Div("No results.")

    res = results[0]
    children.append(_section_header(
        "Memory Distribution by Subarea",
        res.get("source_label", f"generated (rev {revision})"),
        elapsed_ms=res.get("elapsed_ms", 0),
        rows=res.get("row_count", 0),
        cols=res.get("col_count", 0),
    ))

    if not res.get("success"):
        children.append(html.Div(
            [html.I(className="bi bi-x-circle me-2"),
             html.Span(res.get("error", ""))],
            className="dvm-error-card",
        ))
        return html.Div(children)

    df = res.get("df")
    if df is None or df.empty:
        children.append(html.Div("No memory data returned.", className="dvm-empty-state"))
        return html.Div(children)

    try:
        import plotly.graph_objects as go

        chart_df = df.copy()
        chart_df.columns = [c.upper().strip() for c in chart_df.columns]

        label_col = None
        value_col = None
        for col in chart_df.columns:
            if "SUBAREA" in col:
                label_col = col
            elif "DETAIL" in col and not label_col:
                label_col = col
            elif "CATEGORY" in col and not label_col:
                label_col = col

        for col in chart_df.columns:
            if "USED" in col and "GB" in col:
                value_col = col
            elif col == "USED_GB":
                value_col = col
            elif "SIZE_GB" in col and not value_col:
                value_col = col

        if label_col and value_col:
            chart_df[value_col] = pd.to_numeric(chart_df[value_col], errors="coerce")
            chart_df = chart_df.dropna(subset=[value_col])
            # Filter out zero/negative values for pie
            chart_df = chart_df[chart_df[value_col] > 0].head(15)

            fig = go.Figure(data=[go.Pie(
                labels=chart_df[label_col],
                values=chart_df[value_col],
                hole=0.4,
                marker=dict(colors=_CHART_COLORS[:len(chart_df)]),
                textposition="auto",
                textinfo="label+percent",
                hovertemplate="%{label}: %{value:.2f} GB (%{percent})<extra></extra>",
            )])
            fig.update_layout(
                height=420,
                font=dict(family="Figtree, system-ui, -apple-system, sans-serif", size=12, color="#556B82"),
                plot_bgcolor="white",
                paper_bgcolor="white",
                margin=dict(l=20, r=20, t=40, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=-0.15,
                            xanchor="center", x=0.5, font=dict(size=11)),
                title=dict(text="Memory Used (GB) by Subarea", font=dict(size=14)),
            )
            children.append(_chart_card(fig))
        else:
            children.append(html.Div(
                "Chart unavailable: expected SUBAREA + USED_GB columns.",
                className="dvm-warning-card",
            ))

    except ImportError:
        children.append(html.Div("Plotly not installed.", className="dvm-warning-card"))
    except Exception as e:
        children.append(html.Div(f"Chart error: {e}", className="dvm-error-card"))

    children.append(collapsible_sql(res.get("sql", "")))
    children.append(results_table(df, max_rows=100))
    return html.Div(children)


def render_a4(results: List[dict], revision: str) -> html.Div:
    """Render A4 -- Top Growing Tables (Top 10 lists + three detail tables)."""
    children = []

    # Build Top 10 summary section
    top10_section = _build_a4_top10(results)
    if top10_section:
        children.append(top10_section)

    # Detail tables
    labels = [
        "Top Growth by Records (30d)",
        "Top Growth by Disk (30d)",
        "Top Growth by Memory (30d)",
    ]
    for i, res in enumerate(results):
        label = labels[i] if i < len(labels) else f"Result {i+1}"
        src = res.get("source_label", f"generated (rev {revision})")
        children.append(_section_header(label, src,
                                        elapsed_ms=res.get("elapsed_ms", 0),
                                        rows=res.get("row_count", 0),
                                        cols=res.get("col_count", 0)))
        if res.get("success"):
            children.append(results_table(res.get("df"), max_rows=50))
            children.append(collapsible_sql(res.get("sql", "")))
        else:
            children.append(html.Div(
                [html.I(className="bi bi-x-circle me-2"),
                 html.Span(res.get("error", ""))],
                className="dvm-error-card",
            ))
    return html.Div(children)


def _build_a4_top10(results: List[dict]) -> Optional[html.Div]:
    """Build Top 10 summary cards for A4 growth results."""
    categories = ["Records", "Disk", "Memory"]
    cards = []

    for i, res in enumerate(results):
        if not res.get("success") or res.get("df") is None:
            continue
        df = res["df"].copy()
        if df.empty:
            continue

        df.columns = [c.upper().strip() for c in df.columns]
        cat_name = categories[i] if i < len(categories) else f"Category {i+1}"

        # Find table name and growth column
        table_col = next((c for c in df.columns if c == "TABLE_NAME"), None)
        if not table_col:
            table_col = next((c for c in df.columns if "TABLE" in c), None)

        # Growth column: look for GROWTH, DIFF, DELTA, or last numeric column
        growth_col = None
        for c in df.columns:
            if "GROWTH" in c or "DIFF" in c or "DELTA" in c:
                growth_col = c
                break
        if not growth_col:
            # Try the last numeric-looking column
            for c in reversed(list(df.columns)):
                if c != table_col and df[c].dtype in ("float64", "int64"):
                    growth_col = c
                    break
                try:
                    pd.to_numeric(df[c], errors="raise")
                    growth_col = c
                    break
                except (ValueError, TypeError):
                    continue

        if not table_col:
            continue

        # Top 10 list
        top10 = df.head(10)
        items = []
        for idx, row in top10.iterrows():
            tname = str(row.get(table_col, ""))
            gval = ""
            if growth_col and growth_col in row.index:
                try:
                    v = float(row[growth_col])
                    if "GB" in growth_col or "DISK" in growth_col.upper():
                        gval = f"{v:+.2f} GB"
                    elif "MB" in growth_col:
                        gval = f"{v:+.1f} MB"
                    else:
                        gval = f"{v:+,.0f}"
                except (ValueError, TypeError):
                    gval = str(row[growth_col])

            items.append(
                html.Li(
                    [html.Span(tname, style={"fontWeight": "500"}),
                     html.Span(f" ({gval})" if gval else "",
                               style={"color": "var(--dvm-text-secondary)", "fontSize": "11px"})],
                    style={"marginBottom": "3px", "fontSize": "12px"},
                )
            )

        cards.append(
            html.Div(
                [
                    html.Div(
                        [html.I(className="bi bi-arrow-up-right",
                                style={"color": _CHART_COLORS[i % len(_CHART_COLORS)]}),
                         html.Span(f"Top 10 by {cat_name}",
                                   style={"fontWeight": "600", "fontSize": "13px"})],
                        style={"marginBottom": "8px", "display": "flex",
                               "gap": "6px", "alignItems": "center"},
                    ),
                    html.Ol(items, style={"paddingLeft": "18px", "margin": "0"}),
                ],
                style={"flex": "1", "minWidth": "220px", "padding": "12px",
                       "borderRadius": "6px", "border": "1px solid var(--dvm-border)",
                       "backgroundColor": "var(--dvm-bg-subtle, #f8f9fa)"},
            )
        )

    if not cards:
        return None

    return html.Div(
        [
            html.Div(
                [html.I(className="bi bi-trophy me-2",
                        style={"color": "var(--dvm-primary)"}),
                 html.Span("Top 10 Growing Tables (30d Summary)",
                           style={"fontWeight": "600", "fontSize": "14px"})],
                style={"marginBottom": "12px"},
            ),
            html.Div(cards, style={"display": "flex", "gap": "16px", "flexWrap": "wrap",
                                   "marginBottom": "24px"}),
            html.Hr(style={"margin": "0 0 20px", "borderColor": "var(--dvm-border)"}),
        ],
    )


def render_a5(results: List[dict], revision: str) -> html.Div:
    """Render A5 -- Partitioned Tables."""
    children = []
    if not results:
        return html.Div("No results.")

    res = results[0]
    children.append(_section_header(
        "Partitioned Column-Store Tables",
        res.get("source_label", f"generated (rev {revision})"),
        elapsed_ms=res.get("elapsed_ms", 0),
        rows=res.get("row_count", 0),
        cols=res.get("col_count", 0),
    ))
    if res.get("success"):
        children.append(results_table(res.get("df"), max_rows=100))
        children.append(collapsible_sql(res.get("sql", "")))
    else:
        children.append(html.Div(
            [html.I(className="bi bi-x-circle me-2"),
             html.Span(res.get("error", ""))],
            className="dvm-error-card",
        ))
    return html.Div(children)


def render_a6(results: List[dict], revision: str) -> html.Div:
    """Render A6 -- NSE (three sub-tabs)."""
    children = []
    labels = ["NSE Tables", "NSE Partitions", "NSE Columns"]

    sub_tabs = []
    for i, res in enumerate(results):
        label = labels[i] if i < len(labels) else f"Result {i+1}"
        src = res.get("source_label", f"generated (rev {revision})")

        tab_content = []
        tab_content.append(_section_header(label, src,
                                           elapsed_ms=res.get("elapsed_ms", 0),
                                           rows=res.get("row_count", 0),
                                           cols=res.get("col_count", 0)))
        if res.get("success"):
            tab_content.append(results_table(res.get("df"), max_rows=100))
            tab_content.append(collapsible_sql(res.get("sql", "")))
        else:
            tab_content.append(html.Div(
                [html.I(className="bi bi-x-circle me-2"),
                 html.Span(res.get("error", ""))],
                className="dvm-error-card",
            ))

        sub_tabs.append(
            dbc.Tab(
                html.Div(tab_content, style={"padding": "12px 0"}),
                label=label,
                tab_id=f"nse-sub-{i}",
            )
        )

    children.append(
        dbc.Tabs(sub_tabs, id="nse-sub-tabs", active_tab="nse-sub-0")
    )
    return html.Div(children)


# Map analysis_id -> renderer function
RENDERERS = {
    "a1_top_tables": render_a1,
    "a2_db_size_history": render_a2,
    "a3_memory_overview": render_a3,
    "a4_top_growing": render_a4,
    "a5_partitioned_tables": render_a5,
    "a6_nse": render_a6,
}
