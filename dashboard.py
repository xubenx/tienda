import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# ─── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard de Ventas - Aluminios",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS global ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Encabezados de sección */
h2, h3 { color: var(--text-color) !important; }

/* Sidebar responsive al tema */
section[data-testid="stSidebar"] {
    background: var(--secondary-background-color) !important;
}

section[data-testid="stSidebar"] * {
    color: var(--text-color) !important;
}

/* Divider más suave */
hr { border-color: var(--secondary-background-color) !important; margin: 1.2rem 0 !important; }
</style>
""", unsafe_allow_html=True)

st.title("📊 Dashboard de Ventas — Aluminios (Eleventa)")

DB_PATH = Path(__file__).resolve().parent / "MI_BASE.sqlite"

# ─── Conexión ─────────────────────────────────────────────────────────────────
@st.cache_resource
def get_connection():
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

@st.cache_data(ttl=300)
def run_query(sql, params=None):
    con = get_connection()
    cur = con.cursor()
    cur.execute(sql, params or ())
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    df = pd.DataFrame.from_records(rows, columns=cols)
    for col in df.columns:
        if "FECHA" in col.upper() or col.upper().endswith("_EN"):
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df

# ─── Sidebar: filtros ─────────────────────────────────────────────────────────
st.sidebar.header("Filtros")

# Rango de fechas
col1, col2 = st.sidebar.columns(2)
min_date = datetime(2021, 11, 29)
max_date = datetime.now()
fecha_ini = col1.date_input("Desde", value=datetime(2025, 1, 1), min_value=min_date, max_value=max_date)
fecha_fin = col2.date_input("Hasta", value=max_date.date(),     min_value=min_date, max_value=max_date)

# ─── Carga de datos principales ───────────────────────────────────────────────
SQL_TICKETS = """
SELECT
    vt.ID,
    vt.FOLIO,
    vt.VENDIDO_EN,
    vt.SUBTOTAL,
    vt.IMPUESTOS,
    vt.TOTAL,
    vt.GANANCIA,
    vt.ESTA_CANCELADO,
    vt.FORMA_PAGO,
    vt.NUMERO_ARTICULOS,
    u.NOMBRE_COMPLETO AS CAJERO,
    c.NOMBRE AS CAJA
FROM VENTATICKETS vt
LEFT JOIN USUARIOS u ON u.ID = vt.CAJERO_ID
LEFT JOIN CAJAS    c ON c.ID = vt.CAJA_ID
WHERE vt.VENDIDO_EN IS NOT NULL
"""

SQL_LINEAS = """
SELECT
    va.TICKET_ID,
    va.PRODUCTO_CODIGO,
    va.PRODUCTO_NOMBRE,
    va.CANTIDAD,
    va.PRECIO_USADO,
    va.PRECIO_FINAL,
    COALESCE(va.TOTAL_ARTICULO, va.CANTIDAD * va.PRECIO_FINAL) AS TOTAL_ARTICULO,
    va.GANANCIA,
    va.PORCENTAJE_DESCUENTO,
    va.FUE_DEVUELTO,
    d.NOMBRE  AS DEPARTAMENTO,
    vt.VENDIDO_EN,
    vt.ESTA_CANCELADO
FROM VENTATICKETS_ARTICULOS va
JOIN VENTATICKETS vt ON vt.ID = va.TICKET_ID
LEFT JOIN DEPARTAMENTOS d ON d.ID = va.DEPARTAMENTO_ID
WHERE vt.VENDIDO_EN IS NOT NULL
"""

with st.spinner("Cargando datos..."):
    df_all  = run_query(SQL_TICKETS)
    df_lin  = run_query(SQL_LINEAS)

# ─── Aplicar filtros ──────────────────────────────────────────────────────────
mask_all = (df_all["VENDIDO_EN"].dt.date >= fecha_ini) & (df_all["VENDIDO_EN"].dt.date <= fecha_fin)
mask_lin = (df_lin["VENDIDO_EN"].dt.date >= fecha_ini) & (df_lin["VENDIDO_EN"].dt.date <= fecha_fin)

df      = df_all[mask_all].copy()
df_l    = df_lin[mask_lin].copy()

df_activos  = df[df["ESTA_CANCELADO"] == "f"]
df_l_act    = df_l[(df_l["ESTA_CANCELADO"] == "f") & (df_l["FUE_DEVUELTO"] == "f")].copy()

# GANANCIA en VENTATICKETS_ARTICULOS está almacenada como ganancia POR UNIDAD.
# La ganancia real de cada línea = GANANCIA × CANTIDAD.
df_l_act["GANANCIA_TOTAL"] = df_l_act["GANANCIA"] * df_l_act["CANTIDAD"]

# ─── Helpers ──────────────────────────────────────────────────────────────────
def fmt_compact(v: float) -> str:
    """$11.8M  /  $987K  /  $1,234  ó  12,345 (sin $)"""
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:,.0f}"

def fmt_compact_n(v: float) -> str:
    """Para conteos sin símbolo $"""
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"{v/1_000:.1f}K"
    return f"{v:,.0f}"

def kpi_card(icon: str, label: str, compact: str, full: str, color: str = "#4f8ef7") -> str:
    return f"""
    <div class="kpi-card" style="--accent:{color}">
      <span class="kpi-icon">{icon}</span>
      <span class="kpi-label">{label}</span>
      <span class="kpi-value">{compact}</span>
      <span class="kpi-sub">{full}</span>
    </div>"""

# CSS embebido para el iframe de components.html (los estilos globales no aplican dentro del iframe)
_CARD_CSS = """
<style>
body { margin:0; padding:0; background:transparent; overflow:hidden; }
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 12px;
}
@media (max-width: 1200px) { .kpi-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 700px)  { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
.kpi-card {
    background: #1e1e2e;
    border-radius: 10px;
    padding: 16px 18px 14px;
    border-left: 4px solid var(--accent);
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
}
.kpi-icon  { font-size: 1.3rem; line-height: 1; }
.kpi-label { font-size: 0.72rem; color: #9aa0b8; letter-spacing: .04em; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-value { font-size: 1.55rem; font-weight: 700; color: #f0f2ff; line-height: 1.1; white-space: nowrap; }
.kpi-sub   { font-size: 0.72rem; color: #6b7280; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
"""

def render_kpi_grid(grid_html: str, height: int = 130) -> None:
    components.html(_CARD_CSS + grid_html, height=height)

# ─── KPIs principales ─────────────────────────────────────────────────────────
st.subheader("Resumen del período")
tot_ventas   = df_activos["TOTAL"].sum()
tot_ganancia = df_activos["GANANCIA"].sum()
n_tickets    = len(df_activos)
n_cancelados = (df["ESTA_CANCELADO"] == "t").sum()
prom_ticket  = tot_ventas / n_tickets if n_tickets else 0
tot_articulos= df_l_act["CANTIDAD"].sum()
margen_gral  = (tot_ganancia / tot_ventas * 100) if tot_ventas else 0

cards_html = f"""
<div class="kpi-grid">
  {kpi_card("💰","Total vendido",    fmt_compact(tot_ventas),   f"${tot_ventas:,.2f}",   "#4f8ef7")}
  {kpi_card("📈","Ganancia bruta",   fmt_compact(tot_ganancia), f"${tot_ganancia:,.2f}", "#22c55e")}
  {kpi_card("🎯","Margen general",   f"{margen_gral:.1f}%",     f"Ganancia / Ventas",    "#a78bfa")}
  {kpi_card("🧾","Tickets cerrados", fmt_compact_n(n_tickets),  f"{n_tickets:,} ventas", "#38bdf8")}
  {kpi_card("📦","Artículos vendidos",fmt_compact_n(tot_articulos),f"{tot_articulos:,.0f} unidades","#fb923c")}
  {kpi_card("💳","Ticket promedio",  fmt_compact(prom_ticket),  f"${prom_ticket:,.2f} / ticket","#f472b6")}
</div>
"""
render_kpi_grid(cards_html)
st.divider()

# ─── Sección 1: Evolución de ventas ──────────────────────────────────────────
st.subheader("📈 Evolución de ventas")

granularidad = st.radio("Agrupar por", ["Día", "Semana", "Mes", "Año"], horizontal=True, index=2)

freq_map = {"Día": "D", "Semana": "W-MON", "Mes": "ME", "Año": "YE"}
freq = freq_map[granularidad]

ts = df_activos.set_index("VENDIDO_EN").resample(freq).agg(
    TOTAL=("TOTAL", "sum"),
    GANANCIA=("GANANCIA", "sum"),
    TICKETS=("ID", "count"),
).reset_index()

fig_ts = make_subplots(specs=[[{"secondary_y": True}]])
fig_ts.add_trace(go.Bar(x=ts["VENDIDO_EN"], y=ts["TOTAL"],   name="Total vendido",  marker_color="#1f77b4", opacity=0.8), secondary_y=False)
fig_ts.add_trace(go.Bar(x=ts["VENDIDO_EN"], y=ts["GANANCIA"],name="Ganancia",        marker_color="#2ca02c", opacity=0.6), secondary_y=False)
fig_ts.add_trace(go.Scatter(x=ts["VENDIDO_EN"], y=ts["TICKETS"], name="Nº tickets", mode="lines+markers", line=dict(color="#ff7f0e", width=2)), secondary_y=True)
fig_ts.update_layout(barmode="overlay", height=380, legend=dict(orientation="h", y=1.12))
fig_ts.update_yaxes(title_text="$ MXN", secondary_y=False)
fig_ts.update_yaxes(title_text="Tickets", secondary_y=True)
st.plotly_chart(fig_ts, width="stretch")

st.divider()

# ─── Sección 2: Análisis temporal ─────────────────────────────────────────────
st.subheader("🕐 Patrones temporales")
c1, c2 = st.columns(2)

df_activos = df_activos.copy()
df_activos["HORA"]           = df_activos["VENDIDO_EN"].dt.hour
df_activos["DIA_SEMANA_N"]   = df_activos["VENDIDO_EN"].dt.dayofweek
DIAS = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
df_activos["DIA_SEMANA"]     = df_activos["DIA_SEMANA_N"].map(dict(enumerate(DIAS)))

with c1:
    por_hora = df_activos.groupby("HORA").agg(TOTAL=("TOTAL","sum"), TICKETS=("ID","count")).reset_index()
    fig_h = px.bar(por_hora, x="HORA", y="TOTAL", color="TICKETS",
                   color_continuous_scale="Blues",
                   labels={"HORA":"Hora del día","TOTAL":"Venta ($)","TICKETS":"Tickets"},
                   title="Ventas por hora del día")
    fig_h.update_layout(height=340)
    st.plotly_chart(fig_h, width="stretch")

with c2:
    por_dia = df_activos.groupby(["DIA_SEMANA_N","DIA_SEMANA"]).agg(TOTAL=("TOTAL","sum"), TICKETS=("ID","count")).reset_index().sort_values("DIA_SEMANA_N")
    fig_d = px.bar(por_dia, x="DIA_SEMANA", y="TOTAL", color="TICKETS",
                   color_continuous_scale="Oranges",
                   labels={"DIA_SEMANA":"Día","TOTAL":"Venta ($)","TICKETS":"Tickets"},
                   title="Ventas por día de la semana")
    fig_d.update_layout(height=340)
    st.plotly_chart(fig_d, width="stretch")

st.divider()

# ─── Sección 3: Productos más vendidos ───────────────────────────────────────
st.subheader("🏆 Productos más vendidos")
top_n = st.slider("Mostrar top N productos", 5, 50, 20)

c3, c4 = st.columns(2)

top_cant = (
    df_l_act.groupby("PRODUCTO_NOMBRE")
    .agg(CANTIDAD=("CANTIDAD","sum"), INGRESOS=("TOTAL_ARTICULO","sum"))
    .reset_index()
    .sort_values("CANTIDAD", ascending=False)
    .head(top_n)
)
top_ing = (
    df_l_act.groupby("PRODUCTO_NOMBRE")
    .agg(CANTIDAD=("CANTIDAD","sum"), INGRESOS=("TOTAL_ARTICULO","sum"))
    .reset_index()
    .sort_values("INGRESOS", ascending=False)
    .head(top_n)
)

with c3:
    fig_tc = px.bar(top_cant.sort_values("CANTIDAD"), x="CANTIDAD", y="PRODUCTO_NOMBRE",
                    orientation="h", color="INGRESOS", color_continuous_scale="Viridis",
                    title=f"Top {top_n} por Cantidad vendida",
                    labels={"CANTIDAD":"Unidades","PRODUCTO_NOMBRE":"Producto","INGRESOS":"Ingresos $"})
    fig_tc.update_layout(height=max(350, top_n * 20), yaxis_tickfont_size=10)
    st.plotly_chart(fig_tc, width="stretch")

with c4:
    fig_ti = px.bar(top_ing.sort_values("INGRESOS"), x="INGRESOS", y="PRODUCTO_NOMBRE",
                    orientation="h", color="CANTIDAD", color_continuous_scale="Plasma",
                    title=f"Top {top_n} por Ingresos ($)",
                    labels={"INGRESOS":"Ingresos $","PRODUCTO_NOMBRE":"Producto","CANTIDAD":"Unidades"})
    fig_ti.update_layout(height=max(350, top_n * 20), yaxis_tickfont_size=10)
    st.plotly_chart(fig_ti, width="stretch")

st.divider()

# ─── Sección 4: Ventas por departamento ──────────────────────────────────────
st.subheader("🗂️ Ventas por departamento")

depto = (
    df_l_act.groupby("DEPARTAMENTO")
    .agg(INGRESOS=("TOTAL_ARTICULO","sum"), CANTIDAD=("CANTIDAD","sum"), GANANCIA=("GANANCIA_TOTAL","sum"))
    .reset_index()
    .sort_values("INGRESOS", ascending=False)
)
depto["MARGEN_%"] = (depto["GANANCIA"] / depto["INGRESOS"] * 100).round(1)

c5, c6 = st.columns([1.2, 1])
with c5:
    fig_dep = px.bar(depto, x="INGRESOS", y="DEPARTAMENTO", orientation="h",
                     color="MARGEN_%", color_continuous_scale="RdYlGn",
                     hover_data=["CANTIDAD","GANANCIA","MARGEN_%"],
                     title="Ingresos por departamento (color = margen %)",
                     labels={"INGRESOS":"Ingresos $","DEPARTAMENTO":"Departamento"})
    fig_dep.update_layout(height=500, yaxis_tickfont_size=10)
    st.plotly_chart(fig_dep, width="stretch")

with c6:
    fig_pie = px.pie(depto, values="INGRESOS", names="DEPARTAMENTO",
                     title="Distribución de ingresos por departamento",
                     hole=0.4)
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    fig_pie.update_layout(height=500, showlegend=False)
    st.plotly_chart(fig_pie, width="stretch")

st.divider()

# ─── Sección 4b: Drill-down por departamento ─────────────────────────────────
st.subheader("🔍 Análisis detallado por departamento")

deptos_disponibles = sorted(df_l_act["DEPARTAMENTO"].dropna().unique().tolist())
depto_sel = st.selectbox(
    "Selecciona un departamento",
    options=["— Todos los departamentos —"] + deptos_disponibles,
    index=0,
)

if depto_sel == "— Todos los departamentos —":
    df_depto = df_l_act.copy()
    titulo_depto = "Todos los departamentos"
else:
    df_depto = df_l_act[df_l_act["DEPARTAMENTO"] == depto_sel].copy()
    titulo_depto = depto_sel

# KPIs del departamento seleccionado
tot_d   = df_depto["TOTAL_ARTICULO"].sum()
gan_d   = df_depto["GANANCIA_TOTAL"].sum()
cant_d  = df_depto["CANTIDAD"].sum()
prod_d  = df_depto["PRODUCTO_NOMBRE"].nunique()
marg_d  = (gan_d / tot_d * 100) if tot_d > 0 else 0

depto_cards = f"""
<div class="kpi-grid">
  {kpi_card("💰","Ingresos",         fmt_compact(tot_d),          f"${tot_d:,.2f}",         "#4f8ef7")}
  {kpi_card("📈","Ganancia",         fmt_compact(gan_d),          f"${gan_d:,.2f}",          "#22c55e")}
  {kpi_card("🎯","Margen promedio",  f"{marg_d:.1f}%",            "Ganancia / Ingresos",     "#a78bfa")}
  {kpi_card("📦","Unidades",         fmt_compact_n(cant_d),       f"{cant_d:,.0f} uds",      "#fb923c")}
  {kpi_card("🏷️","Productos únicos", fmt_compact_n(prod_d),       f"{prod_d} productos",     "#38bdf8")}
</div>
"""
render_kpi_grid(depto_cards, height=130)

# Resumen por producto dentro del departamento
resumen_depto = (
    df_depto.groupby(["PRODUCTO_CODIGO", "PRODUCTO_NOMBRE"])
    .agg(
        CANTIDAD  =("CANTIDAD",       "sum"),
        INGRESOS  =("TOTAL_ARTICULO", "sum"),
        GANANCIA  =("GANANCIA_TOTAL", "sum"),
        N_VENTAS  =("TICKET_ID",      "nunique"),
    )
    .reset_index()
)
resumen_depto = resumen_depto[resumen_depto["INGRESOS"] > 0].copy()
resumen_depto["MARGEN_%"] = (resumen_depto["GANANCIA"] / resumen_depto["INGRESOS"] * 100).round(1)
resumen_depto["INGRESOS"] = resumen_depto["INGRESOS"].round(2)
resumen_depto["GANANCIA"] = resumen_depto["GANANCIA"].round(2)
resumen_depto["CANTIDAD"] = resumen_depto["CANTIDAD"].round(2)

top_dep_n = st.slider("Top N productos a mostrar en gráficas", 5, 30, 15, key="top_dep")

# ── 3 gráficas: por Ingresos, Ganancia, Margen ────────────────────────────────
gc1, gc2, gc3 = st.columns(3)

with gc1:
    top_ing_d = resumen_depto.nlargest(top_dep_n, "INGRESOS")
    fig_i = px.bar(
        top_ing_d.sort_values("INGRESOS"),
        x="INGRESOS", y="PRODUCTO_NOMBRE", orientation="h",
        color="INGRESOS", color_continuous_scale="Blues",
        title=f"Top {top_dep_n} — Mayor Ingreso ($)",
        labels={"INGRESOS": "Ingresos $", "PRODUCTO_NOMBRE": ""},
    )
    fig_i.update_layout(height=max(380, top_dep_n * 24), yaxis_tickfont_size=9,
                        coloraxis_showscale=False, margin=dict(l=0, r=10))
    st.plotly_chart(fig_i, width="stretch")

with gc2:
    top_gan_d = resumen_depto.nlargest(top_dep_n, "GANANCIA")
    fig_g = px.bar(
        top_gan_d.sort_values("GANANCIA"),
        x="GANANCIA", y="PRODUCTO_NOMBRE", orientation="h",
        color="GANANCIA", color_continuous_scale="Greens",
        title=f"Top {top_dep_n} — Mayor Ganancia ($)",
        labels={"GANANCIA": "Ganancia $", "PRODUCTO_NOMBRE": ""},
    )
    fig_g.update_layout(height=max(380, top_dep_n * 24), yaxis_tickfont_size=9,
                        coloraxis_showscale=False, margin=dict(l=0, r=10))
    st.plotly_chart(fig_g, width="stretch")

with gc3:
    top_marg_d = resumen_depto[resumen_depto["INGRESOS"] >= 500].nlargest(top_dep_n, "MARGEN_%")
    fig_m = px.bar(
        top_marg_d.sort_values("MARGEN_%"),
        x="MARGEN_%", y="PRODUCTO_NOMBRE", orientation="h",
        color="MARGEN_%", color_continuous_scale="RdYlGn",
        title=f"Top {top_dep_n} — Mayor Margen % <br><sup>(productos con ingresos ≥ $500)</sup>",
        labels={"MARGEN_%": "Margen %", "PRODUCTO_NOMBRE": ""},
        range_color=[0, max(top_marg_d["MARGEN_%"].max(), 1)] if not top_marg_d.empty else [0, 100],
    )
    fig_m.update_layout(height=max(380, top_dep_n * 24), yaxis_tickfont_size=9,
                        coloraxis_showscale=False, margin=dict(l=0, r=10))
    st.plotly_chart(fig_m, width="stretch")

# ── Tabla completa del departamento ───────────────────────────────────────────
st.markdown(f"**Tabla completa — {titulo_depto}**")

tabla_depto = resumen_depto.sort_values("INGRESOS", ascending=False).rename(columns={
    "PRODUCTO_CODIGO": "Código",
    "PRODUCTO_NOMBRE": "Producto",
    "CANTIDAD":        "Unidades",
    "INGRESOS":        "Ingresos $",
    "GANANCIA":        "Ganancia $",
    "MARGEN_%":        "Margen %",
    "N_VENTAS":        "# Ventas",
})

st.dataframe(
    tabla_depto[["Código","Producto","Unidades","Ingresos $","Ganancia $","Margen %","# Ventas"]],
    width="stretch", height=380,
)

csv_dep = tabla_depto.to_csv(index=False).encode("utf-8")
nombre_csv = depto_sel.replace(" ", "_").replace("/", "-") if depto_sel != "— Todos los departamentos —" else "todos"
st.download_button(
    f"⬇️ Descargar — {titulo_depto}",
    csv_dep, f"productos_{nombre_csv}.csv", "text/csv",
    key="dl_depto",
)

st.divider()

# ─── Sección 5: Métodos de pago ───────────────────────────────────────────────
st.subheader("💳 Formas de pago")

forma_map = {"e": "Efectivo", "c": "Tarjeta/Crédito", "s": "Saldo/Otro"}
df_activos["FORMA_LABEL"] = df_activos["FORMA_PAGO"].str.strip().map(forma_map).fillna("Otro")

pago = df_activos.groupby("FORMA_LABEL").agg(
    TOTAL=("TOTAL","sum"), TICKETS=("ID","count")
).reset_index()

c7, c8 = st.columns(2)
with c7:
    fig_pago1 = px.pie(pago, values="TOTAL", names="FORMA_LABEL",
                       title="Distribución por monto ($)", hole=0.4,
                       color_discrete_sequence=px.colors.qualitative.Set2)
    fig_pago1.update_traces(textinfo="percent+value+label")
    fig_pago1.update_layout(height=320, showlegend=False)
    st.plotly_chart(fig_pago1, width="stretch")

with c8:
    fig_pago2 = px.pie(pago, values="TICKETS", names="FORMA_LABEL",
                       title="Distribución por número de tickets", hole=0.4,
                       color_discrete_sequence=px.colors.qualitative.Set2)
    fig_pago2.update_traces(textinfo="percent+value+label")
    fig_pago2.update_layout(height=320, showlegend=False)
    st.plotly_chart(fig_pago2, width="stretch")

st.divider()

# ─── Sección 6: Mapa de calor ventas por día/hora ────────────────────────────
st.subheader("🗓️ Mapa de calor: ventas por hora y día")

df_activos["DIA_SEMANA_LABEL"] = df_activos["DIA_SEMANA_N"].map(dict(enumerate(DIAS)))
heat = df_activos.groupby(["DIA_SEMANA_N","DIA_SEMANA_LABEL","HORA"]).agg(TOTAL=("TOTAL","sum")).reset_index()
heat_pivot = heat.pivot(index="DIA_SEMANA_N", columns="HORA", values="TOTAL").fillna(0)
heat_pivot.index = [DIAS[i] for i in heat_pivot.index]

fig_heat = px.imshow(heat_pivot, aspect="auto", color_continuous_scale="YlOrRd",
                     labels={"x":"Hora","y":"Día","color":"Ventas $"},
                     title="Mapa de calor — Ventas ($) por día y hora")
fig_heat.update_layout(height=350)
st.plotly_chart(fig_heat, width="stretch")

st.divider()

# ─── Sección 7: Margen por producto ──────────────────────────────────────────
st.subheader("💰 Análisis de margen por producto (Top 30)")

margen_prod = (
    df_l_act[df_l_act["TOTAL_ARTICULO"] > 0]
    .groupby("PRODUCTO_NOMBRE")
    .agg(INGRESOS=("TOTAL_ARTICULO","sum"), GANANCIA=("GANANCIA_TOTAL","sum"), CANTIDAD=("CANTIDAD","sum"))
    .reset_index()
)
margen_prod["MARGEN_%"] = (margen_prod["GANANCIA"] / margen_prod["INGRESOS"] * 100).round(1)
margen_prod = margen_prod[margen_prod["INGRESOS"] > 100].sort_values("INGRESOS", ascending=False).head(30)

fig_marg = px.scatter(margen_prod, x="INGRESOS", y="MARGEN_%", size="CANTIDAD",
                       color="MARGEN_%", color_continuous_scale="RdYlGn",
                       hover_name="PRODUCTO_NOMBRE",
                       labels={"INGRESOS":"Ingresos ($)","MARGEN_%":"Margen (%)","CANTIDAD":"Unidades"},
                       title="Ingresos vs Margen por producto (tamaño = cantidad vendida)")
fig_marg.update_layout(height=420)
st.plotly_chart(fig_marg, width="stretch")

st.divider()

# ─── Sección 8: Tabla detallada de productos ─────────────────────────────────
st.subheader("📋 Tabla detallada de productos")

resumen_prod = (
    df_l_act.groupby(["PRODUCTO_CODIGO","PRODUCTO_NOMBRE","DEPARTAMENTO"])
    .agg(
        CANTIDAD   =("CANTIDAD","sum"),
        INGRESOS   =("TOTAL_ARTICULO","sum"),
        GANANCIA   =("GANANCIA_TOTAL","sum"),
        N_VENTAS   =("TICKET_ID","nunique"),
    )
    .reset_index()
    .sort_values("INGRESOS", ascending=False)
)
resumen_prod["MARGEN_%"] = (resumen_prod["GANANCIA"] / resumen_prod["INGRESOS"] * 100).where(resumen_prod["INGRESOS"] > 0).round(1)
resumen_prod["INGRESOS"]  = resumen_prod["INGRESOS"].round(2)
resumen_prod["GANANCIA"]  = resumen_prod["GANANCIA"].round(2)
resumen_prod["CANTIDAD"]  = resumen_prod["CANTIDAD"].round(2)

st.dataframe(
    resumen_prod.rename(columns={
        "PRODUCTO_CODIGO":"Código","PRODUCTO_NOMBRE":"Producto","DEPARTAMENTO":"Departamento",
        "CANTIDAD":"Unidades","INGRESOS":"Ingresos $","GANANCIA":"Ganancia $","N_VENTAS":"# Ventas","MARGEN_%":"Margen %"
    }),
    width="stretch", height=400
)

# Descarga CSV
csv = resumen_prod.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Descargar tabla como CSV", csv, "productos_ventas.csv", "text/csv")

st.divider()

# ─── Catálogo de productos para análisis de costos ───────────────────────────
df_prod_cat = run_query("SELECT CODIGO, DESCRIPCION, PCOSTO, PVENTA, DINVENTARIO FROM PRODUCTOS")
df_prod_cat["PCOSTO"] = pd.to_numeric(df_prod_cat["PCOSTO"], errors="coerce").fillna(0)
df_prod_cat["PVENTA"] = pd.to_numeric(df_prod_cat["PVENTA"], errors="coerce").fillna(0)
df_prod_cat = df_prod_cat.drop_duplicates(subset=["CODIGO"])

# ─── Sección 9: Costos de materiales y presión de margen ─────────────────────
st.subheader("🧱 Costos de materiales y presión de margen")
st.caption("Cruce de ventas del período con catálogo de productos (PCOSTO = precio de compra registrado).")

costos = resumen_prod.merge(
    df_prod_cat[["CODIGO", "PCOSTO", "PVENTA"]],
    left_on="PRODUCTO_CODIGO",
    right_on="CODIGO",
    how="left",
)
costos["PCOSTO"] = pd.to_numeric(costos["PCOSTO"], errors="coerce").fillna(0)
costos["PVENTA"] = pd.to_numeric(costos["PVENTA"], errors="coerce").fillna(0)
costos["CANTIDAD"] = pd.to_numeric(costos["CANTIDAD"], errors="coerce").fillna(0)
costos["INGRESOS"] = pd.to_numeric(costos["INGRESOS"], errors="coerce").fillna(0)
costos["GANANCIA"] = pd.to_numeric(costos["GANANCIA"], errors="coerce").fillna(0)
costos["MARGEN_%"] = pd.to_numeric(costos["MARGEN_%"], errors="coerce")

costos_validos = costos[costos["INGRESOS"] > 0].copy()

if costos_validos.empty:
    st.warning("No hay información suficiente de ventas para analizar costos en el período seleccionado.")
else:
    costos_validos["DEPARTAMENTO"] = costos_validos["DEPARTAMENTO"].fillna("Sin departamento")
    costos_validos["COSTO_COMPRA_TOTAL"] = costos_validos["PCOSTO"] * costos_validos["CANTIDAD"]
    costos_validos["COSTO_EST_UNIT"] = (
        (costos_validos["INGRESOS"] - costos_validos["GANANCIA"]) / costos_validos["CANTIDAD"]
    ).where(costos_validos["CANTIDAD"] > 0)

    umbral_ventas = costos_validos["CANTIDAD"].quantile(0.75)
    umbral_margen = costos_validos["MARGEN_%"].quantile(0.25)

    criticos = costos_validos[
        (costos_validos["CANTIDAD"] >= umbral_ventas)
        & (costos_validos["MARGEN_%"] <= umbral_margen)
    ].copy()

    if criticos.empty:
        criticos = costos_validos.sort_values(["CANTIDAD", "MARGEN_%"], ascending=[False, True]).head(15).copy()

    total_costo_compra = costos_validos["COSTO_COMPRA_TOTAL"].sum()
    costo_prom_unit = (total_costo_compra / costos_validos["CANTIDAD"].sum()) if costos_validos["CANTIDAD"].sum() > 0 else 0
    pct_ingresos_crit = (criticos["INGRESOS"].sum() / costos_validos["INGRESOS"].sum() * 100) if costos_validos["INGRESOS"].sum() > 0 else 0

    costos_cards = f"""
<div class="kpi-grid" style="grid-template-columns:repeat(4,1fr)">
  {kpi_card("🛒", "Costo compra acumulado", fmt_compact(total_costo_compra), f"${total_costo_compra:,.2f}", "#f59e0b")}
  {kpi_card("📦", "Costo compra prom. unit", fmt_compact(costo_prom_unit), f"${costo_prom_unit:,.2f} por unidad", "#38bdf8")}
  {kpi_card("⚠️", "Productos críticos", fmt_compact_n(len(criticos)), f"Alta venta + bajo margen", "#ef4444")}
  {kpi_card("🎯", "% ingresos en críticos", f"{pct_ingresos_crit:.1f}%", "Participación sobre ingresos", "#a78bfa")}
</div>"""
    render_kpi_grid(costos_cards, height=130)

    # ── Costo compra promedio unitario por departamento ─────────────────────
    costo_dep = (
        costos_validos.groupby("DEPARTAMENTO")
        .agg(
            UNIDADES=("CANTIDAD", "sum"),
            INGRESOS=("INGRESOS", "sum"),
            GANANCIA=("GANANCIA", "sum"),
            COSTO_COMPRA_TOTAL=("COSTO_COMPRA_TOTAL", "sum"),
            PRODUCTOS=("PRODUCTO_CODIGO", "nunique"),
        )
        .reset_index()
    )
    costo_dep["COSTO_COMPRA_PROM_UNIT"] = (
        costo_dep["COSTO_COMPRA_TOTAL"] / costo_dep["UNIDADES"]
    ).where(costo_dep["UNIDADES"] > 0)
    costo_dep["MARGEN_%"] = (
        costo_dep["GANANCIA"] / costo_dep["INGRESOS"] * 100
    ).where(costo_dep["INGRESOS"] > 0)
    costo_dep = costo_dep.sort_values("COSTO_COMPRA_PROM_UNIT", ascending=False)

    st.markdown("### 🏬 Costo compra prom. unit por departamento")
    dep_c1, dep_c2 = st.columns([1.2, 1])

    with dep_c1:
        fig_dep_cost = px.bar(
            costo_dep.sort_values("COSTO_COMPRA_PROM_UNIT"),
            x="COSTO_COMPRA_PROM_UNIT",
            y="DEPARTAMENTO",
            orientation="h",
            color="MARGEN_%",
            color_continuous_scale="RdYlGn_r",
            title="Costo promedio unitario de compra por departamento",
            labels={
                "COSTO_COMPRA_PROM_UNIT": "Costo compra prom. unit $",
                "DEPARTAMENTO": "Departamento",
                "MARGEN_%": "Margen %",
            },
        )
        fig_dep_cost.update_layout(height=max(340, len(costo_dep) * 26), yaxis_tickfont_size=10)
        st.plotly_chart(fig_dep_cost, width="stretch")

    with dep_c2:
        fig_dep_sc = px.scatter(
            costo_dep,
            x="COSTO_COMPRA_PROM_UNIT",
            y="MARGEN_%",
            size="UNIDADES",
            color="INGRESOS",
            hover_name="DEPARTAMENTO",
            color_continuous_scale="Viridis",
            title="Relación costo unitario vs margen (tamaño = unidades)",
            labels={
                "COSTO_COMPRA_PROM_UNIT": "Costo prom. unit $",
                "MARGEN_%": "Margen %",
                "UNIDADES": "Unidades",
                "INGRESOS": "Ingresos $",
            },
        )
        fig_dep_sc.update_layout(height=max(340, len(costo_dep) * 26))
        st.plotly_chart(fig_dep_sc, width="stretch")

    tabla_dep = costo_dep.rename(columns={
        "DEPARTAMENTO": "Departamento",
        "UNIDADES": "Unidades",
        "INGRESOS": "Ingresos $",
        "GANANCIA": "Ganancia $",
        "COSTO_COMPRA_TOTAL": "Costo compra total $",
        "COSTO_COMPRA_PROM_UNIT": "Costo compra prom. unit $",
        "MARGEN_%": "Margen %",
        "PRODUCTOS": "# Productos",
    })
    tabla_dep["Unidades"] = tabla_dep["Unidades"].round(2)
    tabla_dep["Ingresos $"] = tabla_dep["Ingresos $"].round(2)
    tabla_dep["Ganancia $"] = tabla_dep["Ganancia $"].round(2)
    tabla_dep["Costo compra total $"] = tabla_dep["Costo compra total $"].round(2)
    tabla_dep["Costo compra prom. unit $"] = tabla_dep["Costo compra prom. unit $"].round(2)
    tabla_dep["Margen %"] = tabla_dep["Margen %"].round(1)

    st.dataframe(
        tabla_dep[
            [
                "Departamento", "Costo compra prom. unit $", "Margen %", "Unidades",
                "Ingresos $", "Ganancia $", "Costo compra total $", "# Productos",
            ]
        ],
        width="stretch",
        height=min(420, 120 + len(tabla_dep) * 28),
    )

    csv_dep_cost = tabla_dep.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar CSV — Costo prom. unit por departamento",
        csv_dep_cost,
        "costo_promedio_unitario_por_departamento.csv",
        "text/csv",
        key="dl_costo_dep",
    )

    c_cost1, c_cost2 = st.columns(2)

    with c_cost1:
        top_costo_abs = costos_validos.nlargest(15, "COSTO_COMPRA_TOTAL")
        fig_costo = px.bar(
            top_costo_abs.sort_values("COSTO_COMPRA_TOTAL"),
            x="COSTO_COMPRA_TOTAL", y="PRODUCTO_NOMBRE", orientation="h",
            color="MARGEN_%", color_continuous_scale="RdYlGn",
            title="Top 15 — Mayor costo de compra acumulado (PCOSTO × unidades)",
            labels={"COSTO_COMPRA_TOTAL": "Costo compra $", "PRODUCTO_NOMBRE": "Producto", "MARGEN_%": "Margen %"},
        )
        fig_costo.update_layout(height=420, yaxis_tickfont_size=9, margin=dict(l=0, r=10))
        st.plotly_chart(fig_costo, width="stretch")

    with c_cost2:
        crit_plot = criticos.sort_values(["CANTIDAD", "MARGEN_%"], ascending=[True, True]).tail(15)
        fig_crit = px.bar(
            crit_plot,
            x="CANTIDAD", y="PRODUCTO_NOMBRE", orientation="h",
            color="MARGEN_%", color_continuous_scale="RdYlGn_r",
            title="Top 15 — Alta venta con menor margen",
            labels={"CANTIDAD": "Unidades", "PRODUCTO_NOMBRE": "Producto", "MARGEN_%": "Margen %"},
        )
        fig_crit.update_layout(height=420, yaxis_tickfont_size=9, margin=dict(l=0, r=10))
        st.plotly_chart(fig_crit, width="stretch")

    st.markdown("**Productos de mayor venta con menor margen (revisar precio/costo/proveedor)**")
    tabla_crit = (
        criticos[[
            "PRODUCTO_CODIGO", "PRODUCTO_NOMBRE", "DEPARTAMENTO", "CANTIDAD",
            "INGRESOS", "GANANCIA", "MARGEN_%", "PCOSTO", "PVENTA", "COSTO_EST_UNIT",
        ]]
        .sort_values(["CANTIDAD", "MARGEN_%"], ascending=[False, True])
        .rename(columns={
            "PRODUCTO_CODIGO": "Código",
            "PRODUCTO_NOMBRE": "Producto",
            "DEPARTAMENTO": "Departamento",
            "CANTIDAD": "Unidades",
            "INGRESOS": "Ingresos $",
            "GANANCIA": "Ganancia $",
            "MARGEN_%": "Margen %",
            "PCOSTO": "Costo compra unit $",
            "PVENTA": "Precio venta cat $",
            "COSTO_EST_UNIT": "Costo estimado unit $",
        })
    )
    tabla_crit["Unidades"] = tabla_crit["Unidades"].round(2)
    tabla_crit["Ingresos $"] = tabla_crit["Ingresos $"].round(2)
    tabla_crit["Ganancia $"] = tabla_crit["Ganancia $"].round(2)
    tabla_crit["Margen %"] = tabla_crit["Margen %"].round(1)
    tabla_crit["Costo compra unit $"] = tabla_crit["Costo compra unit $"].round(2)
    tabla_crit["Precio venta cat $"] = tabla_crit["Precio venta cat $"].round(2)
    tabla_crit["Costo estimado unit $"] = tabla_crit["Costo estimado unit $"].round(2)

    st.dataframe(tabla_crit, width="stretch", height=360)

    csv_crit = tabla_crit.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar CSV — Productos críticos de margen",
        csv_crit,
        "productos_criticos_margen.csv",
        "text/csv",
        key="dl_crit_margen",
    )

    # ── Mapas de calor de costos y margen ────────────────────────────────────
    st.markdown("### 🔥 Mapas de calor (costos y margen)")
    hm1, hm2 = st.columns(2)

    with hm1:
        heat_dep_vals = costo_dep[["DEPARTAMENTO", "COSTO_COMPRA_PROM_UNIT", "MARGEN_%", "UNIDADES", "INGRESOS"]].copy()
        heat_dep_vals = heat_dep_vals.set_index("DEPARTAMENTO")

        heat_norm = heat_dep_vals.copy()
        for col in heat_norm.columns:
            cmin = heat_norm[col].min()
            cmax = heat_norm[col].max()
            if pd.notna(cmin) and pd.notna(cmax) and cmax > cmin:
                heat_norm[col] = (heat_norm[col] - cmin) / (cmax - cmin)
            else:
                heat_norm[col] = 0

        heat_norm = heat_norm.rename(columns={
            "COSTO_COMPRA_PROM_UNIT": "Costo unit",
            "MARGEN_%": "Margen %",
            "UNIDADES": "Unidades",
            "INGRESOS": "Ingresos",
        }).fillna(0)

        fig_heat_dep = px.imshow(
            heat_norm,
            aspect="auto",
            color_continuous_scale="Turbo",
            labels={"x": "Métrica", "y": "Departamento", "color": "Intensidad"},
            title="Intensidad por departamento (0-1)",
        )
        fig_heat_dep.update_layout(height=max(340, len(heat_norm) * 28))
        st.plotly_chart(fig_heat_dep, width="stretch")

    with hm2:
        dep_top_heat = costo_dep.nlargest(10, "INGRESOS")["DEPARTAMENTO"].tolist()
        df_heat_dep_hora = df_l_act.copy()
        df_heat_dep_hora["DEPARTAMENTO"] = df_heat_dep_hora["DEPARTAMENTO"].fillna("Sin departamento")
        df_heat_dep_hora = df_heat_dep_hora[df_heat_dep_hora["DEPARTAMENTO"].isin(dep_top_heat)].copy()
        if not df_heat_dep_hora.empty:
            df_heat_dep_hora["HORA"] = pd.to_datetime(df_heat_dep_hora["VENDIDO_EN"]).dt.hour
            dep_hora = (
                df_heat_dep_hora.groupby(["DEPARTAMENTO", "HORA"])
                .agg(INGRESOS=("TOTAL_ARTICULO", "sum"))
                .reset_index()
            )
            pivot_dep_hora = dep_hora.pivot(index="DEPARTAMENTO", columns="HORA", values="INGRESOS").fillna(0)

            fig_heat_dep_hora = px.imshow(
                pivot_dep_hora,
                aspect="auto",
                color_continuous_scale="YlOrRd",
                labels={"x": "Hora", "y": "Departamento", "color": "Ingresos $"},
                title="Mapa de calor — Ingresos por hora y departamento",
            )
            fig_heat_dep_hora.update_layout(height=max(340, len(pivot_dep_hora) * 28))
            st.plotly_chart(fig_heat_dep_hora, width="stretch")
        else:
            st.info("No hay datos suficientes para el mapa de calor por hora/departamento.")

st.divider()

# ─── Sección 10: Productos con costo $0 ──────────────────────────────────────
st.subheader("⚠️ Productos con costo registrado en $0")
st.caption("Productos cuyo PCOSTO = 0 en el catálogo: toda la venta es ganancia contable. Puede indicar costo no registrado o productos de servicio.")

codigos_cero = set(df_prod_cat[df_prod_cat["PCOSTO"] == 0]["CODIGO"].tolist())
n_prods_catalogo = len(codigos_cero)

df_cero = df_l_act[df_l_act["PRODUCTO_CODIGO"].isin(codigos_cero)].copy()

if df_cero.empty:
    st.success("✅ No se encontraron ventas de productos con costo $0 en el período seleccionado.")
else:
    n_prods_vendidos = df_cero["PRODUCTO_NOMBRE"].nunique()
    total_rev_cero   = df_cero["TOTAL_ARTICULO"].sum()
    total_cant_cero  = df_cero["CANTIDAD"].sum()
    total_gan_cero   = df_cero["GANANCIA_TOTAL"].sum()
    pct_ventas       = (total_rev_cero / tot_ventas * 100) if tot_ventas > 0 else 0

    cero_cards = f"""
<div class="kpi-grid" style="grid-template-columns:repeat(5,1fr)">
  {kpi_card("⚠️", "En catálogo (costo $0)", fmt_compact_n(n_prods_catalogo), f"{n_prods_catalogo} productos", "#ef4444")}
  {kpi_card("📊", "Vendidos en período",    fmt_compact_n(n_prods_vendidos), f"de {n_prods_catalogo} con costo $0", "#f97316")}
  {kpi_card("💰", "Ingresos generados",     fmt_compact(total_rev_cero),     f"${total_rev_cero:,.2f}", "#22c55e")}
  {kpi_card("📦", "Unidades vendidas",      fmt_compact_n(total_cant_cero),  f"{total_cant_cero:,.0f} uds", "#38bdf8")}
  {kpi_card("📈", "% del total ventas",     f"{pct_ventas:.1f}%",            "Del período filtrado", "#a78bfa")}
</div>"""
    render_kpi_grid(cero_cards, height=130)

    resumen_cero = (
        df_cero.groupby(["PRODUCTO_CODIGO", "PRODUCTO_NOMBRE"])
        .agg(
            CANTIDAD  =("CANTIDAD",       "sum"),
            INGRESOS  =("TOTAL_ARTICULO", "sum"),
            GANANCIA  =("GANANCIA_TOTAL", "sum"),
            N_VENTAS  =("TICKET_ID",      "nunique"),
        )
        .reset_index()
        .sort_values("INGRESOS", ascending=False)
    )
    resumen_cero["MARGEN_%"] = (resumen_cero["GANANCIA"] / resumen_cero["INGRESOS"] * 100).where(resumen_cero["INGRESOS"] > 0).round(1)
    resumen_cero["INGRESOS"] = resumen_cero["INGRESOS"].round(2)
    resumen_cero["GANANCIA"] = resumen_cero["GANANCIA"].round(2)
    resumen_cero["CANTIDAD"] = resumen_cero["CANTIDAD"].round(2)

    cc1, cc2 = st.columns([1, 1.2])

    with cc1:
        top_cero = resumen_cero.head(20)
        fig_cero = px.bar(
            top_cero.sort_values("INGRESOS"),
            x="INGRESOS", y="PRODUCTO_NOMBRE", orientation="h",
            color="INGRESOS", color_continuous_scale="Reds",
            title=f"Top 20 — Ingresos de productos con costo $0",
            labels={"INGRESOS": "Ingresos $", "PRODUCTO_NOMBRE": "Producto"},
        )
        fig_cero.update_layout(
            height=max(380, min(20, len(top_cero)) * 26),
            yaxis_tickfont_size=9,
            coloraxis_showscale=False,
            margin=dict(l=0, r=10),
        )
        st.plotly_chart(fig_cero, width="stretch")

    with cc2:
        st.markdown("**Todos los productos con costo $0 vendidos en el período**")
        st.dataframe(
            resumen_cero.rename(columns={
                "PRODUCTO_CODIGO": "Código",
                "PRODUCTO_NOMBRE": "Producto",
                "CANTIDAD":        "Unidades",
                "INGRESOS":        "Ingresos $",
                "GANANCIA":        "Ganancia $",
                "MARGEN_%":        "Margen %",
                "N_VENTAS":        "# Ventas",
            })[["Código","Producto","Unidades","Ingresos $","Ganancia $","Margen %","# Ventas"]],
            width="stretch", height=380,
        )
        csv_cero = resumen_cero.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar CSV — Costo $0",
            csv_cero, "productos_costo_cero.csv", "text/csv",
            key="dl_cero",
        )

# ─── Footer ───────────────────────────────────────────────────────────────────
st.caption(f"Base de datos: MI_BASE.sqlite | Datos actualizados: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
