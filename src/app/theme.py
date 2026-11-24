"""Visual layer: palette, CSS, stat band and Plotly chart builders.

Design direction: a clinical ledger. Cool mint paper, deep pine ink, and one
high-contrast colour reserved for owner personal spending, so the story of the
data is legible before anyone reads a number. Figures are set in Georgia, the
way a printed statement sets its figures, while the interface stays in the
system sans. No web fonts: the clinic runs this offline.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

PAPER = "#F4F8F6"
INK = "#10241F"
PINE = "#0B4F45"
TEAL = "#11796C"
AMBER = "#C98A2E"
RUST = "#A8412B"
RULE = "#D6E1DC"
MUTED = "#5C6F69"
WHITE = "#FFFFFF"

SANS = ('-apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif')
SERIF = 'Georgia, "Iowan Old Style", "Times New Roman", serif'

CSS = f"""
<style>
:root {{
  --paper: {PAPER}; --ink: {INK}; --pine: {PINE}; --teal: {TEAL};
  --amber: {AMBER}; --rust: {RUST}; --rule: {RULE}; --muted: {MUTED};
  --white: {WHITE};
}}
[data-testid="stAppViewContainer"] {{ background: var(--paper); }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbar"] {{ right: 1rem; }}
.block-container {{ padding-top: 2.4rem; padding-bottom: 4.5rem; max-width: 1180px; }}

html, body {{ font-family: {SANS}; color: var(--ink); }}
p, li, label, [data-testid="stMarkdownContainer"] {{ color: var(--ink); }}

h1 {{
  font-family: {SERIF}; font-weight: 400; font-size: 2.05rem;
  letter-spacing: -0.015em; margin-bottom: 0.15rem;
}}
h2, h3 {{ font-family: {SANS}; font-weight: 600; letter-spacing: -0.005em; }}
h2 {{ font-size: 1.1rem; margin-top: 1.6rem; }}
h3 {{ font-size: 0.95rem; }}
h2 + div, h3 + div {{ margin-top: 0.4rem; }}

.lede {{ color: var(--muted); font-size: 0.94rem; line-height: 1.5;
         max-width: 68ch; margin: 0 0 1.5rem; }}

.band {{ display: grid; grid-template-columns: repeat(4, 1fr);
         border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule);
         margin: 0.4rem 0 1.8rem; }}
.band > div {{ padding: 1rem 1.3rem 1.1rem 0; border-right: 1px solid var(--rule); }}
.band > div:last-child {{ border-right: none; padding-right: 0; }}
.band .k {{ font-size: 0.79rem; color: var(--muted); margin-bottom: 0.3rem; }}
.band .v {{ font-family: {SERIF}; font-size: 1.72rem; line-height: 1.15;
            font-variant-numeric: tabular-nums; }}
.band .n {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.28rem; }}
@media (max-width: 900px) {{
  .band {{ grid-template-columns: repeat(2, 1fr); }}
  .band > div {{ border-bottom: 1px solid var(--rule); }}
}}

[data-testid="stSidebar"] {{ background: #EAF1EE; border-right: 1px solid var(--rule); }}
[data-testid="stSidebar"] .block-container {{ padding-top: 2rem; }}
.brand {{ font-family: {SERIF}; font-size: 1.02rem; line-height: 1.3; color: var(--k, var(--ink)); }}
.brand span {{ display: block; font-family: {SANS}; font-size: 0.76rem;
               color: var(--muted); margin-top: 0.3rem; }}

[data-testid="stMetric"] {{ border-top: 1px solid var(--rule); padding-top: 0.75rem; }}
[data-testid="stMetricLabel"] p {{ color: var(--muted); font-size: 0.79rem; }}
[data-testid="stMetricValue"] {{ font-family: {SERIF}; font-weight: 400;
                                 font-size: 1.55rem; }}
[data-testid="stMetricDelta"] {{ font-size: 0.78rem; }}

[data-testid="stDataFrame"] {{ border: 1px solid var(--rule); border-radius: 3px; }}
[data-testid="stExpander"] details {{ border: 1px solid var(--rule); border-radius: 3px;
                                      background: transparent; }}

.stButton > button, .stDownloadButton > button {{
  border-radius: 3px; border: 1px solid var(--rule); background: var(--paper);
  color: var(--ink); font-weight: 500; font-size: 0.88rem; padding: 0.4rem 0.9rem;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  border-color: var(--teal); color: var(--pine);
}}
.stButton > button[kind="primary"] {{ background: var(--pine); border-color: var(--pine);
                                      color: var(--white); }}
button[data-testid="stBaseButton-primary"] {{ background: var(--pine) !important;
  border-color: var(--pine) !important; }}
button[data-testid="stBaseButton-primary"] p,
button[data-testid="stBaseButton-primary"] span,
button[data-testid="stBaseButton-primary"] div {{ color: var(--white) !important; }}
.stButton > button[kind="primary"]:hover {{ background: var(--teal); border-color: var(--teal);
                                            color: var(--white); }}

[data-testid="stTabs"] button[role="tab"] {{ color: var(--muted); font-size: 0.9rem;
                                             padding: 0.45rem 0.1rem; }}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{ color: var(--ink);
  border-bottom-color: var(--teal); }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background: var(--teal); }}

hr {{ border-color: var(--rule); }}
[data-testid="stRadio"] label p {{ font-size: 0.92rem; }}
[data-testid="stCaptionContainer"] p, .stCaption {{ color: var(--muted); font-size: 0.8rem; }}
</style>
"""


def money(value: float) -> str:
    return f"₱{value:,.0f}"


def band(items: list[tuple[str, str, str]]) -> str:
    """One statement-style strip of figures: (label, value, note)."""
    cells = "".join(
        f'<div><div class="k">{label}</div>'
        f'<div class="v">{value}</div>'
        f'<div class="n">{note}</div></div>'
        for label, value, note in items
    )
    return f'<div class="band">{cells}</div>'


def lede(text: str) -> str:
    return f'<p class="lede">{text}</p>'


def _money_axis(fig: go.Figure, axis: str = "y") -> go.Figure:
    target = fig.update_yaxes if axis == "y" else fig.update_xaxes
    target(tickprefix="₱", tickformat="~s")
    return fig


def _style(fig: go.Figure, height: int, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Segoe UI, Roboto, Helvetica Neue, Arial", size=12,
                  color=INK),
        margin=dict(l=6, r=6, t=10, b=6),
        hoverlabel=dict(bgcolor=WHITE, bordercolor=RULE,
                        font=dict(color=INK, size=12)),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(size=11, color=MUTED), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, zeroline=False, linecolor=RULE,
                   ticks="", tickfont=dict(size=11, color=MUTED)),
        yaxis=dict(gridcolor=RULE, zeroline=False, showline=False,
                   tickfont=dict(size=11, color=MUTED)),
        bargap=0.34,
        hovermode="x unified",
    )
    return fig


def monthly_cash(monthly: pd.DataFrame) -> go.Figure:
    x = monthly["period"].dt.strftime("%b %y")
    fig = go.Figure()
    fig.add_bar(x=x, y=monthly["operating"], name="Operating",
                marker_color=AMBER, marker_line_width=0)
    fig.add_bar(x=x, y=monthly["personal"], name="Owner personal",
                marker_color=RUST, marker_line_width=0)
    fig.add_scatter(x=x, y=monthly["collected"], name="Collections",
                    mode="lines+markers",
                    line=dict(color=PINE, width=1.4),
                    marker=dict(color=PINE, size=6))
    fig.update_layout(barmode="stack")
    return _money_axis(_style(fig, 330))


def cost_mix(cats: pd.DataFrame) -> go.Figure:
    d = cats.head(8).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d["total"], y=d["category"], orientation="h",
        marker_color=[RUST if c == "Unclassified" else TEAL for c in d["category"]],
        marker_line_width=0,
        text=[f"{s:.0%}" for s in d["share"]],
        textposition="outside",
        textfont=dict(size=11, color=MUTED),
        hovertemplate="%{y}: ₱%{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(bargap=0.45)
    fig.update_xaxes(showgrid=True, gridcolor=RULE)
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11, color=INK),
                     tickprefix=None)
    return _money_axis(_style(fig, 300, legend=False), axis="x")


def weekday(profile: dict) -> go.Figure:
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dow = {int(k): float(v) for k, v in profile["dow_mean"].items()}
    vals = [dow.get(i, 0.0) for i in range(7)]
    colors = [MUTED if i == 6 else TEAL for i in range(7)]
    fig = go.Figure(go.Bar(x=names, y=vals, marker_color=colors,
                           marker_line_width=0,
                           hovertemplate="%{x}: ₱%{y:,.0f}<extra></extra>"))
    fig.add_hline(y=profile["overall_mean"], line_dash="dot", line_color=PINE,
                  line_width=1.2)
    fig.update_yaxes(range=[0, max(vals) * 1.16])
    fig.update_layout(showlegend=False)
    return _money_axis(_style(fig, 300, legend=False))


def projection(actual: pd.DataFrame, proj: pd.DataFrame,
               lo: float, hi: float, n_context: int = 6) -> go.Figure:
    a = actual.tail(n_context)
    fig = go.Figure()
    xa = a["period"]
    xp = proj["period"]
    fig.add_scatter(x=xp, y=proj["point"] + hi, mode="lines",
                    line=dict(width=0), hoverinfo="skip", showlegend=False)
    fig.add_scatter(x=xp, y=proj["point"] + lo, mode="lines",
                    line=dict(width=0), fill="tonexty",
                    fillcolor="rgba(17,121,108,0.13)",
                    name="80% range", hoverinfo="skip", showlegend=False)
    fig.add_scatter(x=xa, y=a["collected"], name="Actual", mode="lines+markers",
                    line=dict(color=PINE, width=2), legendrank=1,
                    marker=dict(size=6, color=PINE))
    fig.add_scatter(x=xp, y=proj["point"], name="Projected", mode="lines+markers",
                    line=dict(color=TEAL, width=2, dash="dot"), legendrank=2,
                    marker=dict(size=7, color=TEAL))
    fig.add_vline(x=pd.Timestamp(a["period"].iloc[-1]), line_width=1,
                  line_dash="dot", line_color=RULE)
    fig.update_xaxes(tickformat="%b %y")
    return _money_axis(_style(fig, 330)).update_yaxes(rangemode="tozero")


def pacing(split: pd.DataFrame) -> go.Figure:
    s = split.copy()
    s["week"] = s["week_end"].dt.strftime("%d %b")
    fig = go.Figure(go.Bar(x=s["week"], y=s["point"], marker_color=TEAL,
                           marker_line_width=0,
                           hovertemplate="week ending %{x}: ₱%{y:,.0f}<extra></extra>"))
    fig.update_layout(showlegend=False)
    return _money_axis(_style(fig, 270, legend=False))


def backtest(bt: pd.DataFrame, chosen: str, baseline: str) -> go.Figure:
    fig = go.Figure()
    actual = bt[bt["model"] == chosen]
    fig.add_scatter(x=actual["period"], y=actual["actual"], name="Actual",
                    mode="lines", line=dict(color=PINE, width=2))
    fig.add_scatter(x=actual["period"], y=actual["predicted"], name=chosen,
                    mode="lines", line=dict(color=TEAL, width=2, dash="dot"))
    base = bt[bt["model"] == baseline]
    fig.add_scatter(x=base["period"], y=base["predicted"], name=baseline,
                    mode="lines", line=dict(color=MUTED, width=1, dash="dash"))
    fig.update_xaxes(tickformat="%b %y")
    return _money_axis(_style(fig, 320))
