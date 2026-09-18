from __future__ import annotations
import base64, io, re, unicodedata
from collections import Counter
import dash
from dash import Dash, dcc, html, dash_table, Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px

APP_TITLE="AVICO Lab 2.0"
DATE_HINTS=["fecha","date","dia","ingreso","nacimiento"]
TIME_HINTS=["hora","time"]
DOCTOR_HINTS=["medico","médico","doctor","responsable","gineco","obstetra"]

def norm(v):
    s="" if v is None else str(v)
    return unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().strip().lower()

def clean_columns(df):
    used=Counter(); cols=[]
    for c in df.columns:
        x=re.sub(r"[^a-z0-9_]+","",norm(c).replace(" ","_")) or "columna"
        used[x]+=1; cols.append(x if used[x]==1 else f"{x}_{used[x]}")
    df=df.copy(); df.columns=cols; return df

def header_score(row):
    vals=[norm(x) for x in row if pd.notna(x)]
    if not vals:return 0
    keys=["fecha","hora","nombre","paciente","expediente","medico","diagnost","edad","turno","proced","cesarea","parto"]
    return sum(any(k in v for k in keys) for v in vals)+min(len(set(vals)),12)*.05

def read_sheet(raw, sheet, engine):
    preview=pd.read_excel(io.BytesIO(raw),sheet_name=sheet,header=None,nrows=20,engine=engine)
    scores=[header_score(preview.iloc[i].tolist()) for i in range(len(preview))]
    h=int(max(range(len(scores)),key=lambda i:scores[i])) if scores else 0
    df=pd.read_excel(io.BytesIO(raw),sheet_name=sheet,header=h,engine=engine)
    df=df.dropna(how="all").dropna(axis=1,how="all")
    return clean_columns(df),h+1

def detect(cols,hints):
    for c in cols:
        if any(norm(h) in norm(c) for h in hints): return c
    return None

def parse(contents,filename):
    raw=base64.b64decode(contents.split(",",1)[1])
    engine="openpyxl" if filename.lower().endswith(".xlsx") else "xlrd"
    book=pd.ExcelFile(io.BytesIO(raw),engine=engine)
    frames=[]; meta=[]
    for sheet in book.sheet_names:
        try:
            df,h=read_sheet(raw,sheet,engine)
            if df.empty: continue
            df["__archivo"]=filename; df["__hoja"]=sheet; df["__fila_encabezado"]=h
            frames.append(df); meta.append((sheet,len(df),len(df.columns),h))
        except Exception as e: meta.append((sheet,0,0,f"ERROR: {e}"))
    return frames,meta

def harmonize(frames):
    if not frames:return pd.DataFrame()
    df=pd.concat(frames,ignore_index=True,sort=False)
    dc=detect(df.columns,DATE_HINTS); tc=detect(df.columns,TIME_HINTS); mc=detect(df.columns,DOCTOR_HINTS)
    if dc:
        raw_date=df[dc]
        # Parse only likely date values; avoid dateutil scanning arbitrary clinical text.
        if pd.api.types.is_numeric_dtype(raw_date):
            df["__fecha"]=pd.to_datetime(raw_date,unit="D",origin="1899-12-30",errors="coerce")
        else:
            ds=raw_date.astype(str).str.strip()
            ds=ds.where(ds.str.match(r"^(?:\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}|\\d{4}[/-]\\d{1,2}[/-]\\d{1,2})$",na=False))
            df["__fecha"]=pd.to_datetime(ds,format="mixed",errors="coerce",dayfirst=True)
    else:
        df["__fecha"]=pd.NaT
    if tc:
        def safe_time(v):
            if pd.isna(v): return None
            if hasattr(v,"strftime"):
                try: return v.strftime("%H:%M")
                except Exception: pass
            x=str(v).strip()
            m=re.search(r"(?<!\\d)([01]?\\d|2[0-3]):([0-5]\\d)(?!\\d)",x)
            return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None
        df["__hora"]=df[tc].map(safe_time)
    else: df["__hora"]=None
    df["__medico"]=df[mc].astype(str) if mc else "No identificado"
    df["__dia"]=df["__fecha"].dt.strftime("%Y-%m-%d").fillna("Sin fecha")
    df["__mes"]=df["__fecha"].dt.strftime("%Y-%m").fillna("Sin fecha")
    hh=pd.to_numeric(pd.Series(df["__hora"]).str[:2],errors="coerce")
    df["__turno"]="Sin hora"
    df.loc[(hh>=7)&(hh<=14),"__turno"]="Matutino"
    df.loc[(hh>=15)&(hh<=21),"__turno"]="Vespertino"
    df.loc[(hh>=22)|(hh<7),"__turno"]="Nocturno"
    return df

app=Dash(__name__,external_stylesheets=[dbc.themes.BOOTSTRAP],title=APP_TITLE)
server=app.server
app.layout=html.Div([
 html.Div([html.Div([html.Div("AVICO",className="brand"),html.Div("Lab 2.0",className="brand-sub")]),html.Div("Laboratorio viviente retrospectivo",className="tagline")],className="topbar"),
 html.Div([
  html.Div([html.H2("Ingesta de datos"),html.P("Sube uno o varios Excel. El sistema inspecciona hojas y busca automáticamente la fila real de encabezados."),
   dcc.Upload(id="up",children=html.Div([html.Div("Seleccionar archivos Excel",className="upload-title"),html.Div(".xlsx / .xls · admite múltiples archivos",className="upload-sub")]),multiple=True,className="upload-box"),
   dcc.Loading(html.Div(id="status",className="status-card"),type="circle"),
   html.Div(id="audit")],className="panel"),
  html.Div([html.Div(id="kpis",className="kpi-grid"),dcc.Dropdown(id="variable",placeholder="Selecciona una variable para analizar"),dcc.Graph(id="chart",config={"displayModeBar":False})],className="panel")
 ],className="page"),
 dcc.Store(id="store",storage_type="memory")
])

@app.callback(Output("store","data"),Output("status","children"),Output("audit","children"),Input("up","contents"),State("up","filename"),prevent_initial_call=True)
def ingest(contents,names):
    if not contents:return dash.no_update,"No se recibieron archivos.",""
    frames=[]; reports=[]; errors=[]
    for c,n in zip(contents,names):
        try:
            fs,meta=parse(c,n); frames+=fs
            reports.append(html.Div([html.B(n),html.Ul([html.Li(f"Hoja {s}: {r:,} filas · {co} columnas · encabezado fila {h}") for s,r,co,h in meta])]))
        except Exception as e: errors.append(f"{n}: {type(e).__name__}: {e}")
    if not frames:
        return None,html.Div(["No pude leer los archivos.",html.Pre("\n".join(errors))]),reports
    df=harmonize(frames)
    # Avoid huge browser payloads: cap preview dataset in MVP.
    maxrows=25000
    clipped=df.head(maxrows)
    payload=clipped.to_json(date_format="iso",orient="split")
    status=html.Div([html.B(f"✓ {len(names)} archivo(s) leído(s) · {len(df):,} registros · {len(df.columns)} variables"),html.Div(f"Vista activa: {len(clipped):,} registros" + (" (límite temporal del MVP)" if len(df)>maxrows else "")),html.Pre("\n".join(errors)) if errors else None])
    return payload,status,reports

@app.callback(Output("variable","options"),Input("store","data"))
def vars(data):
    if not data:return []
    df=pd.read_json(io.StringIO(data),orient="split")
    return [{"label":c,"value":c} for c in df.columns if not c.startswith("__")]

@app.callback(Output("kpis","children"),Output("chart","figure"),Input("store","data"),Input("variable","value"))
def show(data,var):
    empty=px.scatter(title="Carga un Excel para comenzar")
    if not data:return [],empty
    df=pd.read_json(io.StringIO(data),orient="split")
    ks=[html.Div([html.Span("Registros"),html.B(f"{len(df):,}")],className="kpi"),html.Div([html.Span("Variables"),html.B(str(sum(not c.startswith("__") for c in df.columns)))],className="kpi"),html.Div([html.Span("Archivos"),html.B(str(df["__archivo"].nunique()))],className="kpi"),html.Div([html.Span("Hojas"),html.B(str(df["__hoja"].nunique()))],className="kpi")]
    if not var:
        g=df.groupby("__dia").size().reset_index(name="registros"); fig=px.bar(g,x="__dia",y="registros",title="Registros por fecha detectada")
    elif pd.api.types.is_numeric_dtype(df[var]):
        fig=px.histogram(df,x=var,title=f"Distribución: {var}")
    else:
        g=df[var].astype(str).value_counts().head(30).reset_index(); g.columns=[var,"frecuencia"]; fig=px.bar(g,x=var,y="frecuencia",title=f"Frecuencia: {var}")
    fig.update_layout(margin=dict(l=20,r=20,t=55,b=30))
    return ks,fig

if __name__=="__main__": app.run(debug=True,host="0.0.0.0",port=8050)
