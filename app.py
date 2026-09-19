from __future__ import annotations
import base64, io, re, unicodedata
from collections import Counter
import dash
from dash import Dash, dcc, html, dash_table, Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import numpy as np

APP_TITLE="AVICO Lab 2.0"
DATE_HINTS=["fecha","date","dia","ingreso","nacimiento","fn","2026"]
CLEAN_SHEET="base_limpia_2026"
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

def extract_form_sheet(raw, sheet):
    grid=pd.read_excel(io.BytesIO(raw),sheet_name=sheet,header=None,dtype=object,engine="openpyxl")
    out={}
    for row in grid.values.tolist():
        for c,val in enumerate(row):
            if not isinstance(val,str): continue
            label=norm(val).strip(" :")
            if not label or len(label)>55: continue
            for j in range(c+1,min(c+4,len(row))):
                v=row[j]
                if pd.notna(v) and str(v).strip() and norm(v)!=label:
                    key=re.sub(r"[^a-z0-9_]+","_",label.replace(" ","_")).strip("_")
                    if key and key not in out: out[key]=v
                    break
    out["__hoja"]=sheet
    return out

def parse(contents,filename):
    raw=base64.b64decode(contents.split(",",1)[1])
    engine="openpyxl" if filename.lower().endswith(".xlsx") else "xlrd"
    book=pd.ExcelFile(io.BytesIO(raw),engine=engine)
    frames=[]; meta=[]; form_records=[]
    month_names={"enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"}
    sheets = book.sheet_names
    # AVICO-clean exports already contain a canonical analytical table. Prefer it and ignore QC/support sheets.
    canonical = [s for s in sheets if norm(s) == CLEAN_SHEET]
    if canonical:
        sheets = canonical
    for sheet in sheets:
        try:
            if engine=="openpyxl" and norm(sheet) in {"historia clinica","indicaciones","nota de egreso"}:
                rec=extract_form_sheet(raw,sheet)
                rec["__archivo"]=filename; rec["__tipo_hoja"]="formulario"
                form_records.append(rec); meta.append((sheet,1,len(rec),1))
                continue
            df,h=read_sheet(raw,sheet,engine)
            if df.empty: continue
            df["__archivo"]=filename; df["__hoja"]=sheet; df["__fila_encabezado"]=h
            df["__tipo_hoja"]="base_limpia" if norm(sheet)==CLEAN_SHEET else ("mensual" if norm(sheet) in month_names else ("resumen" if norm(sheet)=="resultados" else "auxiliar"))
            # Known birth-book aliases: harmonize structural variants without losing originals.
            aliases={"2026":"fn","hora_24_h":"hora","hora____24_h":"hora","apgar__1_min":"apgar_1_min","apgar_1_min":"apgar_1_min",
                     "apgar_5_min":"apgar_5_min","folio_certificado":"folio_certificado","peso_g":"peso_g","talla_cm":"talla_cm",
                     "pc_cm":"pc_cm","capurro_sdg":"capurro_sdg"}
            ren={c:aliases[c] for c in df.columns if c in aliases and aliases[c] not in df.columns}
            if ren: df=df.rename(columns=ren)
            frames.append(df); meta.append((sheet,len(df),len(df.columns),h))
        except Exception as e: meta.append((sheet,0,0,f"ERROR: {e}"))
    if form_records:
        merged={"__archivo":filename,"__tipo_hoja":"formulario_clinico","__hoja":" + ".join([r["__hoja"] for r in form_records])}
        for rec in form_records:
            prefix=re.sub(r"[^a-z0-9]+","_",norm(rec["__hoja"])).strip("_")
            for k,v in rec.items():
                if not k.startswith("__"): merged[f"{prefix}__{k}"]=v
        frames.append(pd.DataFrame([merged]))
    return frames,meta

def harmonize(frames):
    if not frames:return pd.DataFrame()
    df=pd.concat(frames,ignore_index=True,sort=False)
    # Prefer patient-level sheets for clinical timeline; summaries remain loaded and traceable.
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
   dcc.Upload(id="up",children=html.Div([html.Div("Seleccionar archivos Excel",className="upload-title"),html.Div(".xlsx / .xls · carga masiva: 250+ archivos",className="upload-sub")]),multiple=True,accept=".xlsx,.xls",className="upload-box"),
   dcc.Loading(html.Div(id="status",className="status-card"),type="circle"),
   html.Div(id="audit")],className="panel"),
  html.Div([html.Div(id="kpis",className="kpi-grid"),dcc.Dropdown(id="sheet",placeholder="Todas las pestañas"),dcc.Dropdown(id="variable",placeholder="Selecciona una variable para analizar"),dcc.Graph(id="chart",config={"displayModeBar":False})],className="panel")
 ],className="page"),
 dbc.Button("AI",id="ai-open",className="ai-fab",n_clicks=0),
 dbc.Modal([
  dbc.ModalHeader(dbc.ModalTitle("AVICO AI · Pregunta y cruce estadístico")),
  dbc.ModalBody([
   html.P("Pregunta en lenguaje natural o selecciona variables para explorar asociaciones."),
   dcc.Textarea(id="ai-question",placeholder="Ej.: Cruza edad materna vs vía de nacimiento por mes y dime qué análisis estadístico conviene.",style={"width":"100%","height":"90px"}),
   html.Br(),html.Br(),
   dbc.Row([dbc.Col(dcc.Dropdown(id="ai-x",placeholder="Variable X"),6),dbc.Col(dcc.Dropdown(id="ai-y",placeholder="Variable Y"),6)]),
   html.Br(),dbc.Button("Analizar",id="ai-run",n_clicks=0),html.Hr(),dcc.Loading(html.Div(id="ai-answer"))
  ])
 ],id="ai-modal",is_open=False,size="lg",scrollable=True),
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
    # Canonical AVICO clean-base aliases: preserve all originals while ensuring timeline fields are populated.
    if "fecha" in df.columns:
        df["__fecha"]=pd.to_datetime(df["fecha"],errors="coerce",dayfirst=True)
    if "hora" in df.columns:
        def canon_time(v):
            if pd.isna(v): return None
            if hasattr(v,"strftime"):
                try: return v.strftime("%H:%M")
                except Exception: pass
            x=str(v).strip()
            m=re.search(r"(?<!\\d)([01]?\\d|2[0-3]):([0-5]\\d)(?!\\d)",x)
            return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None
        df["__hora"]=df["hora"].map(canon_time)
    if "medico_valoracion" in df.columns:
        df["__medico"]=df["medico_valoracion"].fillna("No identificado").astype(str)
    if "turno" in df.columns:
        df["__turno"]=df["turno"].fillna("Sin hora").astype(str).str.title()
    df["__dia"]=df["__fecha"].dt.strftime("%Y-%m-%d").fillna("Sin fecha")
    df["__mes"]=df["__fecha"].dt.strftime("%Y-%m").fillna("Sin fecha")
    # Avoid huge browser payloads: cap preview dataset in MVP.
    maxrows=25000
    clipped=df.head(maxrows)
    payload=clipped.to_json(date_format="iso",orient="split")
    status=html.Div([html.B(f"✓ {len(names)} archivo(s) leído(s) · {len(df):,} registros · {len(df.columns)} variables"),html.Div(f"Vista activa: {len(clipped):,} registros" + (" (límite temporal del MVP)" if len(df)>maxrows else "")),html.Pre("\n".join(errors)) if errors else None])
    return payload,status,reports

@app.callback(Output("variable","options"),Output("sheet","options"),Input("store","data"))
def vars(data):
    if not data:return [],[]
    df=pd.read_json(io.StringIO(data),orient="split")
    vo=[{"label":c,"value":c} for c in df.columns if not c.startswith("__")]
    so=[{"label":s,"value":s} for s in sorted(df["__hoja"].dropna().astype(str).unique())]
    return vo,so

@app.callback(Output("kpis","children"),Output("chart","figure"),Input("store","data"),Input("variable","value"),Input("sheet","value"))
def show(data,var,sheet):
    empty=px.scatter(title="Carga un Excel para comenzar")
    if not data:return [],empty
    df=pd.read_json(io.StringIO(data),orient="split")
    if sheet: df=df[df["__hoja"]==sheet]
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

@app.callback(Output("ai-modal","is_open"),Input("ai-open","n_clicks"),prevent_initial_call=True)
def toggle_ai(n): return True

@app.callback(Output("ai-x","options"),Output("ai-y","options"),Input("store","data"))
def ai_options(data):
    if not data:return [],[]
    df=pd.read_json(io.StringIO(data),orient="split")
    opts=[{"label":c,"value":c} for c in df.columns if not c.startswith("__")]
    return opts,opts

def variable_kind(x):
    n=x.dropna()
    if pd.api.types.is_numeric_dtype(n): return "numérica"
    u=n.astype(str).nunique()
    return "categórica" if u<=30 else "texto/alta cardinalidad"

@app.callback(Output("ai-answer","children"),Input("ai-run","n_clicks"),State("store","data"),State("ai-question","value"),State("ai-x","value"),State("ai-y","value"),prevent_initial_call=True)
def ai_analysis(n,data,q,x,y):
    if not data:return dbc.Alert("Primero carga un libro Excel.",color="warning")
    df=pd.read_json(io.StringIO(data),orient="split")
    if not x and not y:
        return html.Div([html.B("Pregunta recibida: "),q or "Sin pregunta",html.P("Selecciona Variable X y Variable Y para realizar un cruce reproducible sobre los datos cargados.")])
    cards=[]
    for v in [x,y]:
        if v and v in df:
            k=variable_kind(df[v]); valid=int(df[v].notna().sum()); missing=int(df[v].isna().sum())
            cards.append(html.P([html.B(v),f": {k} · válidos {valid:,} · faltantes {missing:,}"]))
    recommendation=""
    result=""
    if x and y and x in df and y in df:
        kx,ky=variable_kind(df[x]),variable_kind(df[y])
        d=df[[x,y]].dropna()
        if kx=="numérica" and ky=="numérica":
            recommendation="Sugerencia: correlación de Spearman como exploración robusta; Pearson si se cumplen linealidad y supuestos."
            if len(d)>=3:
                rho=d[x].rank().corr(d[y].rank()); result=f"Spearman exploratorio ρ = {rho:.3f} · n = {len(d):,}."
        elif kx=="categórica" and ky=="categórica":
            tab=pd.crosstab(d[x],d[y]); recommendation="Sugerencia: χ² de independencia; usar Fisher/exacto cuando las frecuencias esperadas sean pequeñas."
            result=f"Tabla de contingencia: {tab.shape[0]} × {tab.shape[1]} categorías · n = {len(d):,}."
        else:
            num=x if kx=="numérica" else (y if ky=="numérica" else None)
            cat=y if num==x else x
            recommendation="Sugerencia: comparar distribución entre grupos; t/ANOVA si se justifican sus supuestos, o Mann–Whitney/Kruskal–Wallis como alternativas."
            if num:
                g=d.groupby(cat)[num].agg(["count","mean","median"]).head(20).round(2)
                result="Resumen por grupos: "+ "; ".join(f"{idx}: n={int(r['count'])}, media={r['mean']}, mediana={r['median']}" for idx,r in g.iterrows())
    return html.Div([html.Div(cards),html.P([html.B("Pregunta: "),q or "Cruce seleccionado"]),dbc.Alert(recommendation or "Selecciona dos variables para recomendar el análisis.",color="info"),html.P(result)])

