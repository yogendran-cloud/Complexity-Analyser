"""Streamlit dashboard for the trusted bundled Complexity Analyzer samples."""

from __future__ import annotations

import tempfile
from html import escape
from pathlib import Path

import streamlit as st

from complexity_analyzer import AnalysisError, ComplexityReport, complexity
from sample_algorithms import (
    constant,
    exponential,
    linear,
    linearithmic,
    logarithmic,
    quadratic,
)


ALGORITHMS = {
    "Constant — return a value": (constant, "2, 4, 8, 16, 32", 1_000_000),
    "Logarithmic — halve until one": (logarithmic, "16, 64, 256, 1024, 4096", 10_000_000),
    "Linear — sum a range": (linear, "1000, 2000, 4000, 8000, 16000", 200_000),
    "Linearithmic — repeated passes": (linearithmic, "128, 256, 512, 1024, 2048", 10_000),
    "Quadratic — count all pairs": (quadratic, "20, 40, 80, 160, 320", 500),
    "Exponential — count binary strings": (exponential, "4, 6, 8, 10, 12", 16),
}

STATUS_LABELS = {
    "plausible": ("Plausible estimate", "The measurements support one candidate under the estimator's checks. This is not proof."),
    "tentative": ("Tentative estimate", "The estimate has meaningful uncertainty; treat it as exploratory."),
    "inconclusive": ("Inconclusive", "The measurements do not clearly distinguish a supported growth pattern."),
}


@st.cache_data(show_spinner=False)
def _make_export(report: ComplexityReport, kind: str) -> bytes:
    """Use the engine's existing file exports and return their bytes."""
    suffix = ".csv" if kind == "csv" else ".svg"
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder) / f"complexity-report{suffix}"
        if kind == "csv":
            report.save_csv(str(output))
        elif kind == "svg":
            report.save_plot(str(output))
        else:
            raise ValueError("Unsupported export format")
        return output.read_bytes()


def _parse_sizes(text: str, maximum: int) -> tuple[int, ...]:
    """Parse and bound a comma-separated sequence of positive integer sizes."""
    try:
        values = tuple(int(part.strip()) for part in text.split(","))
    except ValueError as error:
        raise ValueError("Enter input sizes as comma-separated whole numbers.") from error
    if len(values) < 2:
        raise ValueError("Enter at least two input sizes.")
    if any(value < 1 for value in values):
        raise ValueError("Input sizes must be positive integers.")
    if any(left >= right for left, right in zip(values, values[1:])):
        raise ValueError("Input sizes must be strictly increasing.")
    if values[-1] > maximum:
        raise ValueError(
            f"This sample is capped at input size {maximum:,} to keep analysis bounded."
        )
    return values


def _runtime_display_scale(max_time_seconds: float) -> tuple[float, str]:
    """Choose a readable unit for values stored internally as seconds/call."""
    if max_time_seconds < 0.001:
        return 1_000_000, "µs"
    if max_time_seconds >= 1:
        return 1, "s"
    return 1_000, "ms"


def _has_traced_memory(report: ComplexityReport) -> bool:
    """Return whether any measured size produced a nonzero traced peak."""
    raw_peaks = tuple(
        peak
        for item in report.measurements
        for peak in item.raw_trial_peak_memory_bytes
    )
    if raw_peaks:
        return any(peak > 0 for peak in raw_peaks)
    return any(item.median_peak_memory_bytes > 0 for item in report.measurements)


def _render_report(report: ComplexityReport, algorithm_name: str) -> None:
    st.markdown(
        f'<div class="result-heading"><div><div class="eyebrow">BENCHMARK OUTPUT</div>'
        f'<h2>Analysis results</h2></div><div class="run-context">{escape(algorithm_name)} '
        f'&nbsp;·&nbsp; {len(report.measurements)} sizes &nbsp;·&nbsp; {report.trials} trials</div></div>',
        unsafe_allow_html=True,
    )

    label, explanation = STATUS_LABELS.get(
        report.classification_status,
        ("Unknown status", "The analyzer returned an unrecognized evidence status."),
    )
    status_class = report.classification_status if report.classification_status in STATUS_LABELS else "unknown"
    st.markdown(
        f'<div class="evidence-banner evidence-{status_class}"><div class="evidence-mark"></div>'
        f'<div><div class="evidence-title">{escape(label)}'
        f'{": " + escape(report.estimated_complexity) if status_class != "inconclusive" else " · Best fit: " + escape(report.estimated_complexity)}</div>'
        f'<div class="evidence-copy">{escape(explanation)} {escape(report.classification_note)}</div></div></div>',
        unsafe_allow_html=True,
    )
    if report.classification_status != "plausible":
        st.warning("Treat this label as exploratory; the measurements do not clearly establish a growth class.", icon="⚠️")

    first = report.measurements[0]
    last = report.measurements[-1]
    median_peak = max(item.median_peak_memory_bytes for item in report.measurements)
    maximum_time = max(item.median_time_seconds for item in report.measurements)
    time_scale, time_unit = _runtime_display_scale(maximum_time)
    no_traced_allocations = not _has_traced_memory(report)
    if len(report.measurements) > 1 and first.median_time_seconds > 0:
        time_ratio = last.median_time_seconds / first.median_time_seconds
        runtime_detail = f"{time_ratio:,.2f}× from n={first.input_size:,} to n={last.input_size:,}"
    else:
        runtime_detail = "Across selected input sizes"
    status_detail = {
        "plausible": "One supported shape passed evidence checks",
        "tentative": "Meaningful uncertainty remains",
        "inconclusive": "Candidate models could not be separated",
    }.get(status_class, "Evidence status not recognized")
    memory_value = (
        'No allocations<span class="metric-unit"> detected</span>'
        if no_traced_allocations
        else f'{median_peak:,}<span class="metric-unit"> bytes</span>'
    )
    memory_detail = (
        "No Python-traced allocations detected at these sizes"
        if no_traced_allocations
        else "Largest median across measured sizes"
    )
    status_value_class = {
        "plausible": "metric-status-plausible",
        "tentative": "metric-status-tentative",
        "inconclusive": "metric-status-inconclusive",
    }.get(status_class, "")
    st.markdown(
        '<div class="metric-grid">'
        f'<div class="metric-card metric-cyan"><div class="metric-label">ESTIMATED GROWTH</div>'
        f'<div class="metric-value metric-complexity">{escape(report.estimated_complexity)}</div>'
        f'<div class="metric-foot">Empirical model · not a guarantee</div></div>'
        f'<div class="metric-card metric-violet"><div class="metric-label">EVIDENCE STATUS</div>'
        f'<div class="metric-value metric-status {status_value_class}">{escape(label)}</div>'
        f'<div class="metric-foot">{escape(status_detail)}</div></div>'
        f'<div class="metric-card"><div class="metric-label">MEDIAN RUNTIME</div>'
        f'<div class="metric-value">{last.median_time_seconds * time_scale:.4g}<span class="metric-unit"> {time_unit}</span></div>'
        f'<div class="metric-foot">{escape(runtime_detail)}</div></div>'
        f'<div class="metric-card"><div class="metric-label">PEAK TRACED MEMORY</div>'
        f'<div class="metric-value metric-memory">{memory_value}</div>'
        f'<div class="metric-foot">{escape(memory_detail)}</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.caption("Runtime shown in the summary is the median per-call time at the largest selected input size.")

    rows = [
        {
            "Input size": item.input_size,
            f"Median runtime ({time_unit})": item.median_time_seconds * time_scale,
            f"Timing MAD ({time_unit})": item.time_mad_seconds * time_scale,
            "Peak traced memory (bytes)": item.median_peak_memory_bytes,
        }
        for item in report.measurements
    ]

    st.markdown('<div class="section-kicker">GROWTH PROFILE</div>', unsafe_allow_html=True)

    left_chart, right_chart = st.columns(2)
    with left_chart:
        with st.container(border=True):
            st.markdown(f'<div class="chart-title">Runtime <span>median per call · {escape(time_unit)}</span></div>', unsafe_allow_html=True)
            st.line_chart(
                rows,
                x="Input size",
                y=f"Median runtime ({time_unit})",
                color="#66E3FF",
                width="stretch",
                height=270,
            )
    with right_chart:
        with st.container(border=True):
            st.markdown('<div class="chart-title">Peak traced memory <span>bytes · Python allocations</span></div>', unsafe_allow_html=True)
            if no_traced_allocations:
                st.markdown(
                    '<div class="memory-empty"><div class="memory-empty-mark">—</div>'
                    '<div><div class="memory-empty-title">No traced allocations detected</div>'
                    '<div class="memory-empty-copy">All measured peaks were 0 bytes. '
                    'This means tracemalloc observed no Python allocations at these sizes; '
                    'it does not mean the process uses no memory.</div></div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.line_chart(
                    rows,
                    x="Input size",
                    y="Peak traced memory (bytes)",
                    color="#9B8CFF",
                    width="stretch",
                    height=270,
                )

    with st.expander("Measurement table · median per-size results", expanded=True):
        st.dataframe(rows, hide_index=True, width="stretch")

    st.markdown('<div class="section-kicker">DIAGNOSTICS</div>', unsafe_allow_html=True)
    trial_rows = []
    for item in report.measurements:
        for trial_number, (elapsed, calls, peak) in enumerate(
            zip(
                item.raw_trial_elapsed_seconds,
                item.raw_trial_call_counts,
                item.raw_trial_peak_memory_bytes,
            ),
            start=1,
        ):
            trial_rows.append(
                {
                    "Input size": item.input_size,
                    "Trial": trial_number,
                    "Timed calls": calls,
                    "Elapsed time (ms)": elapsed * 1_000,
                    "Peak traced memory (bytes)": peak,
                }
            )
    with st.expander("Trial-level measurements & methodology", expanded=False):
        st.markdown(
            '<div class="technical-note">Each trial reports elapsed time for the repeated timed calls, '
            'call count, and a separate traced-memory invocation. Per-call time is the timed elapsed '
            'duration divided by the actual call count.</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(trial_rows, hide_index=True, width="stretch")

    csv_bytes = _make_export(report, "csv")
    svg_bytes = _make_export(report, "svg")
    csv_col, svg_col, spacer = st.columns([1, 1, 2])
    with csv_col:
        st.download_button(
            "↓  Export CSV",
            data=csv_bytes,
            file_name="complexity-report.csv",
            mime="text/csv",
            width="stretch",
        )
    with svg_col:
        st.download_button(
            "↓  Export SVG chart",
            data=svg_bytes,
            file_name="complexity-report.svg",
            mime="image/svg+xml",
            width="stretch",
        )


def main() -> None:
    st.set_page_config(
        page_title="Complexity Analyzer",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        :root {
            --midnight: #080b14; --panel: #0d1220; --panel-raised: #111a2b;
            --cyan: #66e3ff; --violet: #9b8cff; --text: #f1f5fc;
            --muted: #b0bdd0; --line: rgba(163, 190, 225, .16);
        }
        html, body, [data-testid="stAppViewContainer"] {
            background: radial-gradient(ellipse at 13% -8%, rgba(47, 111, 153, .17), transparent 38%),
                        radial-gradient(ellipse at 94% 7%, rgba(105, 83, 168, .11), transparent 34%),
                        var(--midnight) !important;
            color: var(--text);
        }
        [data-testid="stHeader"] { background: rgba(8, 11, 20, .72); }
        .block-container { max-width: 1240px; padding: 1.25rem 2.2rem 2.5rem; }
        #MainMenu, footer { visibility: hidden; }
        [data-testid="stAppDeployButton"] { display:none; }
        [data-testid="stToolbar"] { right: 1rem; }
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--line) !important; border-radius: 18px !important;
            background: linear-gradient(145deg, rgba(20, 31, 50, .78), rgba(11, 17, 30, .9));
            box-shadow: 0 18px 44px rgba(0,0,0,.26), inset 0 1px rgba(227,241,255,.065),
                        0 0 0 1px rgba(102,227,255,.018);
        }
        div[data-testid="stForm"] {
            border: 1px solid var(--line); border-radius: 18px; padding: 1.25rem 1.4rem;
            background: linear-gradient(145deg, rgba(16, 24, 40, .83), rgba(10, 15, 27, .82));
            box-shadow: 0 18px 45px rgba(0,0,0,.2), inset 0 1px rgba(255,255,255,.035);
            backdrop-filter: blur(14px);
        }
        h1,h2,h3,p,label { color: var(--text); }
        h1 { letter-spacing: -.045em; font-size: clamp(1.65rem, 3vw, 2.3rem); }
        [data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"] p { color: var(--muted); }
        [data-testid="stCaptionContainer"] p { font-size: .76rem; line-height: 1.55; }
        [data-testid="stWidgetLabel"] p { color: #cbd6e8; font-size: .82rem; font-weight: 600; }
        [data-baseweb="select"] > div, [data-testid="stTextInput"] input {
            background: rgba(7, 12, 22, .84) !important; color: var(--text) !important;
            border: 1px solid rgba(147, 169, 202, .23) !important; border-radius: 10px !important;
            transition: border-color .18s ease, box-shadow .18s ease;
        }
        [data-baseweb="select"] > div:hover, [data-testid="stTextInput"] input:hover {
            border-color: rgba(102, 227, 255, .5) !important;
        }
        [data-baseweb="select"] > div:focus-within, [data-testid="stTextInput"] input:focus {
            border-color: var(--cyan) !important; box-shadow: 0 0 0 3px rgba(102,227,255,.12) !important;
        }
        [data-testid="stSlider"] [role="slider"] { background: var(--cyan); border-color: var(--cyan); }
        [data-testid="stSlider"] [data-testid="stTickBar"] { color: var(--muted); }
        .stButton > button, [data-testid="stFormSubmitButton"] button {
            border: 1px solid rgba(102,227,255,.52) !important; border-radius: 10px !important;
            color: #07121b !important; font-weight: 750 !important; letter-spacing: .01em;
            background: linear-gradient(105deg, #66e3ff, #9cecff 70%, #a8e9f4) !important;
            box-shadow: 0 5px 22px rgba(65, 199, 230, .18), inset 0 1px rgba(255,255,255,.55) !important;
            transition: transform .16s ease, box-shadow .16s ease, filter .16s ease;
        }
        .stButton > button:hover, [data-testid="stFormSubmitButton"] button:hover {
            transform: translateY(-1px); box-shadow: 0 8px 26px rgba(65,199,230,.27) !important; filter: brightness(1.04);
        }
        .stButton > button:focus-visible, [data-testid="stFormSubmitButton"] button:focus-visible {
            outline: 2px solid var(--cyan); outline-offset: 3px;
        }
        [data-testid="stFormSubmitButton"] button:disabled,
        [data-testid="stFormSubmitButton"] button[aria-disabled="true"] {
            color: #506278 !important; border-color: rgba(142,166,195,.18) !important;
            background: linear-gradient(105deg, #253447, #1c2a3c) !important;
            box-shadow: inset 0 1px rgba(255,255,255,.035) !important;
            cursor: not-allowed !important; filter: none !important; transform: none !important;
        }
        [data-testid="stDownloadButton"] button {
            background: rgba(15, 23, 39, .72) !important; color: #c9d7eb !important;
            border: 1px solid rgba(151, 174, 209, .22) !important; border-radius: 10px !important;
            transition: border-color .16s ease, background .16s ease;
        }
        [data-testid="stDownloadButton"] button:hover { border-color: rgba(102,227,255,.55) !important; background: rgba(27,41,62,.88) !important; }
        [data-testid="stDataFrame"], [data-testid="stTable"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
        [data-testid="stVegaLiteChart"] {
            overflow: hidden; border: 1px solid rgba(163,190,225,.12); border-radius: 11px;
            background: linear-gradient(155deg, rgba(8,13,23,.82), rgba(12,18,31,.72));
            box-shadow: inset 0 1px rgba(255,255,255,.025);
        }
        [data-testid="stVegaLiteChart"] svg { overflow: visible; background: transparent !important; }
        [data-testid="stVegaLiteChart"] .role-axis-label text,
        [data-testid="stVegaLiteChart"] .role-axis-title text { fill: #c4d0e0 !important; }
        [data-testid="stVegaLiteChart"] .role-axis-grid line { stroke: rgba(151,174,209,.16) !important; }
        [data-testid="stVegaLiteChart"] .role-axis-tick line,
        [data-testid="stVegaLiteChart"] .role-axis-domain { stroke: rgba(151,174,209,.3) !important; }
        [data-testid="stExpander"] { border: 1px solid var(--line); border-radius: 12px; background: rgba(13,18,32,.55); }
        [data-testid="stAlert"] { border-radius: 12px; border: 1px solid var(--line); }
        [data-testid="stDivider"] { border-color: var(--line); }
        .header-shell { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:.2rem 0 1.45rem; border-bottom:1px solid var(--line); margin-bottom:1.75rem; }
        .brand-lockup { display:flex; align-items:center; gap:.8rem; }
        .brand-mark { width:38px; height:38px; display:grid; place-items:center; border:1px solid rgba(102,227,255,.3); border-radius:12px; background:linear-gradient(145deg,rgba(102,227,255,.12),rgba(155,140,255,.09)); box-shadow:0 0 24px rgba(102,227,255,.08),inset 0 1px rgba(255,255,255,.1); }
        .brand-name { color:var(--text); font-size:.98rem; font-weight:720; letter-spacing:-.02em; }
        .brand-sub { color:#b5c2d5; font-size:.74rem; margin-top:.12rem; }
        .header-tag { color:#c2cede; border:1px solid rgba(163,190,225,.2); background:rgba(13,18,32,.72); border-radius:999px; padding:.44rem .76rem; font-size:.7rem; letter-spacing:.075em; text-transform:uppercase; }
        .hero-copy { margin-bottom:1.15rem; }
        .eyebrow,.section-kicker { color:#8ceaff; font-size:.7rem; font-weight:760; letter-spacing:.14em; text-transform:uppercase; margin-bottom:.36rem; }
        .hero-title { color:var(--text); font-size:clamp(1.3rem,2.5vw,1.9rem); line-height:1.17; font-weight:680; letter-spacing:-.04em; margin:0 0 .45rem; }
        .hero-description { max-width:720px; color:var(--muted); font-size:.91rem; line-height:1.62; margin:0; }
        .panel-heading { color:var(--text); font-size:1rem; font-weight:680; margin:.05rem 0 .2rem; }
        .panel-description { color:#b0bdd0; font-size:.81rem; line-height:1.5; margin-bottom:.85rem; }
        .result-heading { display:flex; justify-content:space-between; align-items:end; gap:1rem; margin:1.5rem 0 .7rem; }
        .result-heading h2 { color:var(--text); font-size:1.35rem; letter-spacing:-.035em; margin:0; }
        .run-context { color:#b0bdd0; font-size:.78rem; text-align:right; }
        .evidence-banner { display:flex; gap:.8rem; align-items:flex-start; padding:.9rem 1rem; margin:.65rem 0 1rem; border:1px solid var(--line); border-radius:13px; background:rgba(13,18,32,.68); }
        .evidence-mark { flex:0 0 8px; width:8px; height:8px; border-radius:50%; margin-top:.37rem; background:var(--cyan); box-shadow:0 0 12px currentColor; }
        .evidence-plausible { border-color:rgba(85,211,164,.25); background:rgba(34,104,83,.12); }
        .evidence-plausible .evidence-mark { background:#55d3a4; }
        .evidence-tentative { border-color:rgba(255,190,92,.29); background:rgba(113,74,27,.13); }
        .evidence-tentative .evidence-mark { background:#ffbe5c; }
        .evidence-inconclusive,.evidence-unknown { border-color:rgba(255,117,130,.26); background:rgba(119,42,57,.14); }
        .evidence-inconclusive .evidence-mark,.evidence-unknown .evidence-mark { background:#ff7582; }
        .evidence-title { color:var(--text); font-weight:680; font-size:.9rem; }
        .evidence-copy { color:#b0bdd0; font-size:.79rem; line-height:1.55; margin-top:.22rem; }
        .metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); align-items:stretch; gap:.72rem; margin:.7rem 0 .2rem; }
        .metric-card { min-height:122px; display:flex; flex-direction:column; position:relative; overflow:hidden; padding:.95rem 1rem .88rem; border:1px solid rgba(163,190,225,.17); border-radius:15px; background:linear-gradient(145deg,rgba(20,31,50,.9),rgba(10,15,27,.91)); box-shadow:0 15px 36px rgba(0,0,0,.22),inset 0 1px rgba(240,248,255,.055),inset 0 -1px rgba(0,0,0,.16); transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease; }
        .metric-card:after { content:""; position:absolute; width:120px; height:120px; border-radius:50%; right:-70px; top:-76px; background:radial-gradient(circle,rgba(102,227,255,.1),transparent 68%); pointer-events:none; }
        .metric-card:hover { transform:translateY(-2px); border-color:rgba(132,174,207,.25); box-shadow:0 18px 42px rgba(0,0,0,.25),inset 0 1px rgba(255,255,255,.05); }
        .metric-cyan { border-top-color:rgba(102,227,255,.42); }
        .metric-violet { border-top-color:rgba(155,140,255,.46); }
        .metric-label { color:#b3c0d3; font-size:.68rem; font-weight:760; letter-spacing:.105em; }
        .metric-value { color:var(--text); min-height:2.35rem; display:flex; align-items:center; flex-wrap:wrap; gap:.18rem; font-size:1.42rem; line-height:1.2; font-weight:700; letter-spacing:-.04em; margin:.42rem 0 .25rem; }
        .metric-complexity { color:var(--cyan); font-size:1.72rem; text-shadow:0 0 22px rgba(102,227,255,.2); }
        .metric-status { font-size:1.03rem; letter-spacing:-.02em; }
        .metric-status-plausible { color:#72e0b1; }
        .metric-status-tentative { color:#ffd080; }
        .metric-status-inconclusive { color:#ff9aa4; }
        .metric-memory { font-size:1.12rem; letter-spacing:-.025em; }
        .metric-unit { color:#b7c3d5; font-size:.8rem; font-weight:540; letter-spacing:0; }
        .metric-foot { color:#b0bdd0; font-size:.73rem; line-height:1.45; margin-top:auto; }
        .section-kicker { margin:1.1rem 0 .38rem; color:#b6c5d9; font-size:.7rem; }
        .chart-title { color:var(--text); font-size:.91rem; font-weight:680; margin:.05rem 0 .48rem; }
        .chart-title span { color:#b0bdd0; font-weight:480; font-size:.74rem; margin-left:.35rem; }
        .memory-empty { display:flex; align-items:flex-start; gap:.75rem; min-height:205px; padding:1rem .7rem; border:1px dashed rgba(155,140,255,.28); border-radius:11px; background:linear-gradient(145deg,rgba(155,140,255,.045),rgba(8,13,23,.46)); }
        .memory-empty-mark { flex:0 0 27px; width:27px; height:27px; display:grid; place-items:center; border:1px solid rgba(155,140,255,.25); border-radius:8px; color:#c1b7ff; background:rgba(155,140,255,.08); font-size:1rem; }
        .memory-empty-title { color:#d8d2ff; font-size:.83rem; font-weight:680; margin:.1rem 0 .32rem; }
        .memory-empty-copy { max-width:360px; color:#b5c0d2; font-size:.77rem; line-height:1.6; }
        .technical-note { color:#b3bfd1; font-size:.78rem; line-height:1.6; margin:.2rem 0 .75rem; }
        .empty-state { display:flex; align-items:center; gap:1rem; margin:1rem 0 1.3rem; padding:1.15rem 1.25rem; border:1px dashed rgba(137,166,204,.25); border-radius:15px; background:linear-gradient(120deg,rgba(16,25,42,.68),rgba(10,15,27,.52)); }
        .empty-mark { flex:0 0 38px; height:38px; display:grid; place-items:center; border:1px solid rgba(102,227,255,.2); border-radius:12px; color:var(--cyan); background:rgba(102,227,255,.06); font-size:1rem; }
        .empty-title { color:var(--text); font-size:.87rem; font-weight:660; margin-bottom:.16rem; }
        .empty-copy { color:var(--muted); font-size:.75rem; line-height:1.55; }
        .footer-copy { color:#9eacc1; font-size:.73rem; line-height:1.6; text-align:center; padding:.35rem .5rem; }
        @media (max-width: 850px) { .metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .block-container { padding-left:1.25rem; padding-right:1.25rem; } }
        @media (max-width: 600px) { .block-container { padding:1rem .85rem 2rem; } .header-shell { margin-bottom:1.3rem; } .header-tag { display:none; } .metric-grid { gap:.55rem; } .metric-card { min-height:112px; padding:.8rem .82rem; } .metric-value { font-size:1.2rem; } .metric-complexity { font-size:1.45rem; } .metric-status { font-size:.95rem; } .result-heading { align-items:flex-start; flex-direction:column; gap:.35rem; } .run-context { text-align:left; } .evidence-banner { padding:.8rem; } }
        @media (prefers-reduced-motion: reduce) { *, *:before, *:after { transition:none !important; scroll-behavior:auto !important; } }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="header-shell"><div class="brand-lockup"><div class="brand-mark">'
        '<svg width="21" height="21" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
        '<path d="M4 17.5 9 12l3 3 8-9" stroke="#66E3FF" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M15.5 6H20v4.5" stroke="#9B8CFF" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="4" cy="17.5" r="1.3" fill="#66E3FF"/><circle cx="12" cy="15" r="1.3" fill="#9B8CFF"/>'
        '</svg></div><div><div class="brand-name">Complexity Analyzer</div>'
        '<div class="brand-sub">Empirical performance lab</div></div></div>'
        '<div class="header-tag">MIDNIGHT QUANTUM&nbsp; / &nbsp;DEV TOOL</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="hero-copy"><div class="eyebrow">RUNTIME · MEMORY · GROWTH</div>'
        '<div class="hero-title">Measure the shape of your algorithm.</div>'
        '<p class="hero-description">Benchmark trusted sample functions across input sizes. '
        'Compare median runtime and Python-traced memory, then inspect the evidence behind a heuristic growth estimate.</p></div>',
        unsafe_allow_html=True,
    )

    algorithm_name = st.selectbox("Sample algorithm", tuple(ALGORITHMS), label_visibility="visible")
    function, default_sizes, maximum_size = ALGORITHMS[algorithm_name]
    with st.form("analysis-options"):
        st.markdown('<div class="panel-heading">Benchmark configuration</div>', unsafe_allow_html=True)
        st.markdown('<div class="panel-description">Choose a bundled algorithm and a bounded, increasing input range.</div>', unsafe_allow_html=True)
        algorithm_col, trials_col, sizes_col = st.columns([1.35, .72, 2.2])
        with trials_col:
            trials = st.slider("Trials per input size", min_value=1, max_value=9, value=5)
        with sizes_col:
            size_text = st.text_input(
                "Input sizes (comma-separated)",
                value=default_sizes,
                key=f"input-sizes-{algorithm_name}",
                help=f"Enter increasing positive integers. Maximum for this sample: {maximum_size:,}.",
            )
        with algorithm_col:
            st.markdown(f'<div class="panel-description" style="margin:.35rem 0 0;">Input cap · <b style="color:#c9d7eb">n ≤ {maximum_size:,}</b></div>', unsafe_allow_html=True)
        submitted = st.form_submit_button("Run analysis", type="primary", width="stretch")

    if submitted:
        st.session_state.pop("complexity_report", None)
        try:
            sizes = _parse_sizes(size_text, maximum_size)
            with st.spinner("Measuring the selected sample…"):
                report = complexity(function, sizes=sizes, trials=trials)
            st.session_state["complexity_report"] = (report, algorithm_name)
        except ValueError as error:
            st.error(str(error))
        except AnalysisError as error:
            st.error(f"Analysis could not be completed: {error}")
        except Exception:
            st.error("The analysis failed unexpectedly. Check the selected sample and inputs, then try again.")

    result = st.session_state.get("complexity_report")
    if result is not None:
        report, selected_name = result
        _render_report(report, selected_name)
    else:
        st.markdown(
            '<div class="empty-state"><div class="empty-mark">↗</div><div>'
            '<div class="empty-title">Ready when you are</div>'
            '<div class="empty-copy">Choose a sample, review its input cap, and run an analysis. '
            'Results stay here until you submit another benchmark.</div></div></div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown(
        '<div class="footer-copy">Only bundled trusted samples run in this dashboard. '
        'Timings vary with the machine and system load; traced peak memory is not total process memory. '
        'Empirical growth estimates are evidence, not theoretical guarantees.</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
