from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics import forecast_series, reactive_analysis
from ingestion import extract_report_text, read_table
from telemetry import log_forecast_run, observe, start_metrics_server


st.set_page_config(page_title="Operations Performance Suite", layout="wide")
start_metrics_server()
st.title("Operations & Performance Management Suite")
st.caption("Evidence-based post-mortems and forecasts for operational KPIs")

agent = st.sidebar.radio("Choose agent", ["Reactive post-mortem", "Proactive forecast"])
table_file = st.sidebar.file_uploader("Upload KPI data (CSV/XLSX)", type=["csv", "xlsx", "xls"])
report_file = st.sidebar.file_uploader("Optional Power BI export/screenshot", type=["pdf", "png", "jpg", "jpeg"])

if table_file is None:
    st.info("Upload KPI data, or download and use sample_data/operations_kpis.csv.")
    st.stop()

try:
    df = read_table(table_file)
except Exception as exc:
    st.error(str(exc))
    st.stop()

st.subheader("Data preview")
st.dataframe(df.head(25), use_container_width=True)

date_col = st.selectbox("Date column", df.columns)
numeric_candidates = [c for c in df.columns if c != date_col and pd.to_numeric(df[c], errors="coerce").notna().sum() > 0]
if not numeric_candidates:
    st.error("No numeric KPI column was detected.")
    st.stop()
target = st.selectbox("KPI to analyze", numeric_candidates)

if report_file:
    with st.expander("Extracted report context"):
        st.text(extract_report_text(report_file)[:12000] or "No text detected.")

if agent == "Reactive post-mortem":
    question = st.text_input("Management question", "Why did this KPI deteriorate, and what likely drove it?")
    if st.button("Run post-mortem", type="primary"):
        try:
            with observe("reactive"):
                out = reactive_analysis(df, date_col, target)
            a, b, c = st.columns(3)
            a.metric("Worst value", f"{out['worst_value']:.2f}")
            b.metric("Prior baseline", f"{out['baseline']:.2f}")
            c.metric("Gap vs baseline", f"{out['gap_pct']:.1f}%")
            st.subheader("Evidence-based finding")
            st.write(
                f"The lowest **{target}** occurred on **{out['worst_date'].date()}**. "
                f"It was **{abs(out['gap_pct']):.1f}% {'below' if out['gap_pct'] < 0 else 'above'}** the preceding baseline. "
                "Driver ranking is associative, so validate it against maintenance, staffing, incident, and demand logs before declaring causality."
            )
            if out["drivers"]:
                drivers = pd.DataFrame(out["drivers"])
                st.plotly_chart(go.Figure(go.Bar(x=drivers["importance"], y=drivers["driver"], orientation="h")), use_container_width=True)
            st.subheader("Detected anomalies")
            st.dataframe(out["anomalies"], use_container_width=True)
            st.caption(f"Question recorded: {question}")
        except Exception as exc:
            st.error(str(exc))
else:
    periods = st.slider("Forecast periods", 1, 24, 6)
    threshold = st.number_input("Optional risk threshold", value=0.0, help="Set 0 to disable threshold alerts.")
    if st.button("Generate forecast", type="primary"):
        try:
            with observe("proactive"):
                out = forecast_series(df, date_col, target, periods)
            log_forecast_run(target, periods, out["rmse"])
            hist, fc = out["history"], out["forecast"]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=hist[date_col], y=hist[target], name="Historical actual"))
            fig.add_trace(go.Scatter(x=fc[date_col], y=fc["forecast"], name="Forecast", line=dict(dash="dash")))
            fig.add_trace(go.Scatter(x=pd.concat([fc[date_col], fc[date_col][::-1]]), y=pd.concat([fc["upper_95"], fc["lower_95"][::-1]]), fill="toself", fillcolor="rgba(46,134,222,.15)", line=dict(color="rgba(0,0,0,0)"), name="95% interval"))
            if threshold:
                fig.add_hline(y=threshold, line_dash="dot", annotation_text="Risk threshold")
            st.plotly_chart(fig, use_container_width=True)
            st.metric("In-sample RMSE", f"{out['rmse']:.2f}")
            if threshold:
                breaches = fc.loc[fc["forecast"] > threshold]
                if not breaches.empty:
                    st.warning(f"Projected threshold breach begins {breaches.iloc[0][date_col].date()} ({breaches.iloc[0]['forecast']:.2f}).")
                else:
                    st.success("No threshold breach appears in the selected horizon.")
            st.dataframe(fc, use_container_width=True)
            st.download_button("Download forecast CSV", fc.to_csv(index=False), "forecast.csv", "text/csv")
        except Exception as exc:
            st.error(str(exc))
