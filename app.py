from __future__ import annotations

import base64
import io
import re
import unicodedata
from collections import Counter
from datetime import datetime

import dash
from dash import Dash, dcc, html, dash_table, Input, Output, State
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.express as px


APP_TITLE = "AVICO Lab 2.0"

DOCTORS = [
    "HERNANDEZ ANDRADE YOVANI",
    "HERNANDEZ CETINA IVAN KOWASKY",
    "MACIAS GIL ALEJANDRA CELESTE",
    "HUEZO CASILLAS VICENTE",
    "JIMENEZ VALDEZ VICTORIA",
    "CARDENAS NUÑEZ RAFAEL",
]

DATE_HINTS = ["fecha", "date", "dia", "ingreso", "nacimiento"]
TIME_HINTS = ["hora", "time"]
DOCTOR_HINTS = ["medico", "médico", "doctor", "responsable", "gineco", "obstetra"]
PATIENT_HINTS = ["paciente", "nombre", "expediente", "folio", "nss"]


def norm_text(value):
    s = "" if value is None else str(value)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def normalize_columns(df):
    out = df.copy()
    cols = []
    used = Counter()
    for col in out.columns:
        c = norm_text(col).replace(" ", "_")
        c = re.sub(r"[^a-z0-9_]+", "", c) or "columna"
        used[c] += 1
        if used[c] > 1:
            c = f"{c}_{used[c]}"
        cols.append(c)
    out.columns = cols
    return out


def detect_column(columns, hints):
    scored = []
    for c in columns:
        n = norm_text(c)
        score = sum(1 for h in hints if norm_text(h) in n)
        if score:
            scored.append((score, c))
    return sorted(scored, reverse=True)[0][1] if scored else None


def parse_excel(contents, filename):
    _, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    ext = filename.lower().rsplit(".", 1)[-1]
    engine = "openpyxl" if ext == "xlsx" else "xlrd"
    sheets = pd.read_excel(io.BytesIO(decoded), sheet_name=None, engine=engine)
    frames = []
    for sheet, df in sheets.items():
        if df is None or df.empty:
            continue
        df = normalize_columns(df)
        df["__archivo"] = filename
        df["__hoja"] = sheet
        frames.append(df)
    return frames


def harmonize(frames):
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True, sort=False)
    date_col = detect_column(df.columns, DATE_HINTS)
    time_col = detect_column(df.columns, TIME_HINTS)
    doctor_col = detect_column(df.columns, DOCTOR_HINTS)

    if date_col:
        df["__fecha"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
    else:
        df["__fecha"] = pd.NaT

    if time_col:
        def parse_time(x):
            if pd.isna(x):
                return None
            if isinstance(x, datetime):
                return x.time().strftime("%H:%M")
            s = str(x).strip()
            m = re.search(r"(\d{1,2}):(\d{2})", s)
            return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None
        df["__hora"] = df[time_col].map(parse_time)
    else:
        df["__hora"] = None

    if doctor_col:
        df["__medico_original"] = df[doctor_col].astype(str)
        def match_doc(v):
            nv = norm_text(v)
            scores = []
            for d in DOCTORS:
                toks = [t for t in norm_text(d).split() if len(t) > 3]
                score = sum(t in nv for t in toks)
                scores.append((score, d))
            best = max(scores)
            return best[1] if best[0] >= 1 else str(v)
        df["__medico"] = df[doctor_col].map(match_doc)
    else:
        df["__medico"] = "No identificado"

    if "__fecha" in df and df["__fecha"].notna().any():
        df["__mes"] = df["__fecha"].dt.to_period("M").astype(str)
        df["__dia"] = df["__fecha"].dt.date.astype(str)
        df["__hora_num"] = df["__hora"].str.slice(0, 2)
        df["__hora_num"] = pd.to_numeric(df["__hora_num"], errors="coerce")
        df["__turno"] = np.select(
            [
                (df["__hora_num"] >= 7) & (df["__hora_num"] <= 14),
                (df["__hora_num"] >= 15) & (df["__hora_num"] <= 21),
            ],
            ["Matutino", "Vespertino"],
            default="Nocturno",
        )
    else:
        df["__mes"] = "Sin fecha"
        df["__dia"] = "Sin fecha"
        df["__turno"] = "Sin turno"
    return df


app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], title=APP_TITLE)
server = app.server

STORE = dcc.Store(id="data-store", storage_type="memory")

header = html.Div(
    [
        html.Div([
            html.Div("AVICO", className="brand"),
            html.Div("Lab 2.0", className="brand-sub"),
        ]),
        html.Div("Laboratorio viviente retrospectivo", className="tagline"),
    ],
    className="topbar",
)

upload = dcc.Upload(
    id="upload-data",
    children=html.Div([
        html.Div("Arrastra aquí los archivos Excel", className="upload-title"),
        html.Div("o haz clic para seleccionar múltiples archivos .xlsx / .xls", className="upload-sub"),
    ]),
    multiple=True,
    className="upload-box",
)

app.layout = html.Div([
    STORE,
    header,
    html.Div([
        dbc.Row([
            dbc.Col(html.Div([
                html.H2("Ingesta masiva"),
                html.P("Carga los archivos del periodo. AVICO Lab 2.0 los integra en una sola memoria retrospectiva."),
                upload,
                html.Div(id="upload-status", className="status-card"),
            ], className="panel"), md=4),
            dbc.Col(html.Div([
                html.Div(id="kpis", className="kpi-grid"),
                dbc.Row([
                    dbc.Col(dcc.Dropdown(id="filter-month", placeholder="Mes", clearable=True), md=4),
                    dbc.Col(dcc.Dropdown(id="filter-shift", placeholder="Turno", clearable=True), md=4),
                    dbc.Col(dcc.Dropdown(id="filter-doctor", placeholder="Médico", clearable=True), md=4),
                ], className="filters"),
                dcc.Graph(id="timeline", config={"displayModeBar": False}),
            ], className="panel"), md=8),
        ], className="g-3"),
        dbc.Row([
            dbc.Col(html.Div([
                html.H3("Servicio viviente"),
                dcc.Graph(id="shift-chart", config={"displayModeBar": False}),
            ], className="panel"), md=6),
            dbc.Col(html.Div([
                html.H3("Participación por médico"),
                dcc.Graph(id="doctor-chart", config={"displayModeBar": False}),
            ], className="panel"), md=6),
        ], className="g-3 mt-1"),
        html.Div([
            html.H3("Explorador retrospectivo"),
            html.P("Filtra el histórico y revisa los registros que sustentan cada resultado."),
            dash_table.DataTable(
                id="data-table",
                page_size=15,
                filter_action="native",
                sort_action="native",
                style_table={"overflowX": "auto"},
                style_cell={"fontFamily": "Arial", "fontSize": 12, "padding": "8px", "maxWidth": 220, "whiteSpace": "normal"},
                style_header={"fontWeight": "700"},
            ),
        ], className="panel mt-3"),
    ], className="page"),
], className="app-shell")


@app.callback(
    Output("data-store", "data"),
    Output("upload-status", "children"),
    Input("upload-data", "contents"),
    State("upload-data", "filename"),
    prevent_initial_call=True,
)
def ingest(contents_list, filenames):
    if not contents_list:
        return dash.no_update, ""
    frames, errors = [], []
    for contents, filename in zip(contents_list, filenames):
        try:
            frames.extend(parse_excel(contents, filename))
        except Exception as e:
            errors.append(f"{filename}: {e}")
    df = harmonize(frames)
    payload = df.to_json(date_format="iso", orient="split")
    msg = html.Div([
        html.B(f"{len(filenames)} archivos recibidos · {len(df):,} registros integrados"),
        html.Div(f"{len(errors)} archivos con error" if errors else "Carga completada sin errores"),
        html.Details([html.Summary("Ver errores"), html.Pre("\n".join(errors))]) if errors else None,
    ])
    return payload, msg


@app.callback(
    Output("filter-month", "options"),
    Output("filter-shift", "options"),
    Output("filter-doctor", "options"),
    Input("data-store", "data"),
)
def set_filters(data):
    if not data:
        return [], [], []
    df = pd.read_json(io.StringIO(data), orient="split")
    opts = lambda vals: [{"label": str(v), "value": str(v)} for v in sorted(pd.Series(vals).dropna().astype(str).unique())]
    return opts(df["__mes"]), opts(df["__turno"]), opts(df["__medico"])


@app.callback(
    Output("kpis", "children"),
    Output("timeline", "figure"),
    Output("shift-chart", "figure"),
    Output("doctor-chart", "figure"),
    Output("data-table", "data"),
    Output("data-table", "columns"),
    Input("data-store", "data"),
    Input("filter-month", "value"),
    Input("filter-shift", "value"),
    Input("filter-doctor", "value"),
)
def render(data, month, shift, doctor):
    empty = px.line(title="Carga archivos Excel para iniciar el laboratorio retrospectivo.")
    if not data:
        return [], empty, empty, empty, [], []
    df = pd.read_json(io.StringIO(data), orient="split")
    f = df.copy()
    if month:
        f = f[f["__mes"].astype(str) == month]
    if shift:
        f = f[f["__turno"].astype(str) == shift]
    if doctor:
        f = f[f["__medico"].astype(str) == doctor]

    kpis = [
        html.Div([html.Span("Registros"), html.B(f"{len(f):,}")], className="kpi"),
        html.Div([html.Span("Archivos"), html.B(str(f["__archivo"].nunique()))], className="kpi"),
        html.Div([html.Span("Días"), html.B(str(f["__dia"].nunique()))], className="kpi"),
        html.Div([html.Span("Médicos detectados"), html.B(str(f["__medico"].nunique()))], className="kpi"),
    ]

    daily = f.groupby("__dia", dropna=False).size().reset_index(name="registros")
    fig_t = px.line(daily, x="__dia", y="registros", markers=True, title="Actividad retrospectiva por día")
    fig_t.update_layout(margin=dict(l=20,r=20,t=50,b=20), xaxis_title="", yaxis_title="Registros")

    shifts = f.groupby("__turno").size().reset_index(name="registros")
    fig_s = px.bar(shifts, x="__turno", y="registros")
    fig_s.update_layout(margin=dict(l=20,r=20,t=20,b=20), xaxis_title="", yaxis_title="Registros")

    docs = f.groupby("__medico").size().reset_index(name="registros").sort_values("registros", ascending=True).tail(15)
    fig_d = px.bar(docs, x="registros", y="__medico", orientation="h")
    fig_d.update_layout(margin=dict(l=20,r=20,t=20,b=20), xaxis_title="Registros", yaxis_title="")

    visible = [c for c in f.columns if not c.startswith("__")] + ["__archivo","__hoja","__dia","__hora","__turno","__medico"]
    visible = [c for c in visible if c in f.columns][:30]
    table_df = f[visible].copy().head(2000)
    table_df = table_df.where(pd.notnull(table_df), None)
    cols = [{"name": c, "id": c} for c in visible]
    return kpis, fig_t, fig_s, fig_d, table_df.to_dict("records"), cols


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
