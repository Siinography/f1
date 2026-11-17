"""F1 dashboard: does where you start decide where you finish?

Run locally:  streamlit run app.py
Expects these CSVs in ./data :
  races, results, drivers, constructors, circuits
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="F1: Does the grid decide the race?", layout="wide")


# ---------- 1. Load + clean (document each step in your notebook) ----------
@st.cache_data
def load_data():
    races = pd.read_csv("data/races.csv", na_values=["\\N"])
    results = pd.read_csv("data/results.csv", na_values=["\\N"])
    constructors = pd.read_csv("data/constructors.csv", na_values=["\\N"])
    circuits = pd.read_csv("data/circuits.csv", na_values=["\\N"])

    # Keep only needed columns
    races = races[["raceId", "year", "circuitId", "name"]].rename(columns={"name": "race"})
    results = results[["raceId", "constructorId", "grid", "positionOrder", "position", "points"]]
    constructors = constructors[["constructorId", "name"]].rename(columns={"name": "constructor"})
    circuits = circuits[["circuitId", "name", "country", "lat", "lng"]].rename(columns={"name": "circuit"})

    df = (results.merge(races, on="raceId")
                 .merge(constructors, on="constructorId")
                 .merge(circuits, on="circuitId"))

    # Cleaning step: grid == 0 means pit-lane start / no qualifying time -> drop
    df = df[df["grid"] > 0].copy()
    # Cleaning step: position is NaN when the car did not finish (DNF/DSQ)
    df["finished"] = df["position"].notna()

    # Bucket grid and finish positions for the Sankey
    def grid_bucket(g):
        if g == 1: return "Pole"
        if g <= 3: return "Grid 2-3"
        if g <= 6: return "Grid 4-6"
        if g <= 10: return "Grid 7-10"
        return "Grid 11+"

    def finish_bucket(row):
        if not row["finished"]: return "DNF / DSQ"
        p = row["positionOrder"]
        if p == 1: return "Win"
        if p <= 3: return "Podium"
        if p <= 10: return "Other points zone"
        return "Finished 11+"

    df["grid_bucket"] = df["grid"].apply(grid_bucket)
    df["finish_bucket"] = df.apply(finish_bucket, axis=1)
    return df


df = load_data()

# ---------- 2. Controls (these drive every chart = linked interactivity) ----------
st.title("Does the starting grid decide the race?")
st.caption("Use the sidebar: every chart below updates together.")

with st.sidebar:
    st.header("Filters")
    y0, y1 = int(df.year.min()), 2025  # cap: 2026 is a partial season
    years = st.slider("Seasons", y0, y1, (2000, y1))
    in_range = df[df.year.between(*years)]
    top_teams = in_range.groupby("constructor").size().sort_values(ascending=False).index.tolist()
    teams = st.multiselect("Constructors (empty = all)", top_teams)

f = in_range
if teams:
    f = f[f.constructor.isin(teams)]

if f.empty:
    st.warning("No data for this selection.")
    st.stop()

# ---------- 3. Charts ----------
c1, c2 = st.columns(2)

# Chart 1: bar, wins by constructor
with c1:
    wins = (f[f.positionOrder == 1].groupby("constructor").size()
            .sort_values(ascending=False).head(10).reset_index(name="wins"))
    fig = px.bar(wins, x="wins", y="constructor", orientation="h",
                 title="Race wins by constructor (top 10)")
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)

# Chart 2: line, points per season for top 6 teams
with c2:
    top6 = f.groupby("constructor").points.sum().nlargest(6).index
    pts = (f[f.constructor.isin(top6)].groupby(["year", "constructor"]).points.sum()
           .reset_index())
    fig = px.line(pts, x="year", y="points", color="constructor",
                  title="Points per season (top 6 by points; scoring rules changed over time)")
    st.plotly_chart(fig, use_container_width=True)

c3, c4 = st.columns(2)

# Chart 3: map, circuits, pole-to-win conversion
with c3:
    pole = f[f.grid == 1]
    circ = (pole.groupby(["circuit", "country", "lat", "lng"])
            .agg(poles=("raceId", "nunique"),
                 pole_win_rate=("positionOrder", lambda s: (s == 1).mean() * 100))
            .reset_index())
    fig = px.scatter_geo(circ, lat="lat", lon="lng", size="poles",
                         color="pole_win_rate", hover_name="circuit",
                         color_continuous_scale="Viridis", range_color=(0, 100),
                         title="Circuits: % of pole sitters who won")
    fig.update_layout(coloraxis_colorbar_title="Pole win %")
    fig.update_geos(showland=True, landcolor="#2b2b36", showocean=True,
                    oceancolor="#0e1117", showcountries=True, countrycolor="#555")
    fig.update_layout(height=450, margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True)

# Chart 4 (NEW METHOD): Sankey, grid bucket -> finish bucket
with c4:
    g_order = ["Pole", "Grid 2-3", "Grid 4-6", "Grid 7-10", "Grid 11+"]
    f_order = ["Win", "Podium", "Other points zone", "Finished 11+", "DNF / DSQ"]
    flows = f.groupby(["grid_bucket", "finish_bucket"]).size().reset_index(name="n")
    labels = [f"Start: {g}" for g in g_order] + [f"End: {x}" for x in f_order]
    idx = {l: i for i, l in enumerate(labels)}
    fig = go.Figure(go.Sankey(
        node=dict(label=labels, pad=15, thickness=15),
        link=dict(color="rgba(160,160,160,0.3)",
                  source=[idx[f"Start: {g}"] for g in flows.grid_bucket],
                  target=[idx[f"End: {x}"] for x in flows.finish_bucket],
                  value=flows.n)))
    fig.update_layout(title="Where grid slots end up (Sankey)", height=450, font_size=13)
    st.plotly_chart(fig, use_container_width=True)

st.caption("Data: Ergast-derived F1 results (check the license on your source). "
           f"Showing {len(f):,} race entries.")
