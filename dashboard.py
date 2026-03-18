import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
from datetime import datetime, timedelta, date
from pathlib import Path

st.set_page_config(
    page_title="Dashboard de Ventas - Aluminios",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CSS en bloques pequeños para evitar que Streamlit lo muestre como texto
st.markdown(
    '<style>[data-testid="stVerticalBlock"]>div{padding-bottom:.75rem!important}h2,h3{margin-top:1.25rem!important;margin-bottom:.6rem!important}hr{margin:1.5rem 0!important}iframe{display:block!important;margin-bottom:1rem!important}</style>',
    unsafe_allow_html=True,
)
st.markdown(
    '<style>@media(max-width:768px){section[data-testid="stSidebar"]{display:none!important}.block-container{padding:1rem .5rem!important;max-width:100%!important}h1{font-size:1.4rem!important}h2{font-size:1.1rem!important}h3{font-size:1rem!important}}</style>',
    unsafe_allow_html=True,
)

st.title("📊 Dashboard de Ventas — Aluminios")

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

# ─── Filtros arriba ───────────────────────────────────────────────────────────
hoy = date.today()
min_date = date(2021, 11, 29)

PRESETS = {
    "Este mes":     (hoy.replace(day=1), hoy),
    "Último mes":   ((hoy.replace(day=1) - timedelta(days=1)).replace(day=1), hoy.replace(day=1) - timedelta(days=1)),
    "Últimos 30d":  (hoy - timedelta(days=30), hoy),
    "Últimos 90d":  (hoy - timedelta(days=90), hoy),
    "Este año":     (date(hoy.year, 1, 1), hoy),
    "Año anterior": (date(hoy.year - 1, 1, 1), date(hoy.year - 1, 12, 31)),
    "Todo":         (min_date, hoy),
    "Personalizado": None,
}

filtro_cols = st.columns([1.5, 1, 1, 1])

with filtro_cols[0]:
    preset = st.selectbox(
        "Período",
        options=list(PRESETS.keys()),
        index=4,
        key="preset_sel",
        label_visibility="collapsed",
    )

if preset == "Personalizado":
    with filtro_cols[1]:
        fecha_ini = st.date_input("Desde", value=date(hoy.year, 1, 1), min_value=min_date, max_value=hoy, label_visibility="collapsed")
    with filtro_cols[2]:
        fecha_fin = st.date_input("Hasta", value=hoy, min_value=min_date, max_value=hoy, label_visibility="collapsed")
else:
    fecha_ini, fecha_fin = PRESETS[preset]

with filtro_cols[3]:
    st.caption(f"📅 {fecha_ini.strftime('%d/%m/%Y')} — {fecha_fin.strftime('%d/%m/%Y')}")

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

mask_all = (df_all["VENDIDO_EN"].dt.date >= fecha_ini) & (df_all["VENDIDO_EN"].dt.date <= fecha_fin)
mask_lin = (df_lin["VENDIDO_EN"].dt.date >= fecha_ini) & (df_lin["VENDIDO_EN"].dt.date <= fecha_fin)

df      = df_all[mask_all].copy()
df_l    = df_lin[mask_lin].copy()

df_activos  = df[df["ESTA_CANCELADO"] == "f"]
df_l_act    = df_l[(df_l["ESTA_CANCELADO"] == "f") & (df_l["FUE_DEVUELTO"] == "f")].copy()

df_l_act["GANANCIA_TOTAL"] = df_l_act["GANANCIA"] * df_l_act["CANTIDAD"]

# ─── Helpers ──────────────────────────────────────────────────────────────────
def fmt_compact(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:,.0f}"

def fmt_compact_n(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"{v/1_000:.1f}K"
    return f"{v:,.0f}"

def kpi_card(icon: str, label: str, compact: str, full: str, color: str = "#4f8ef7") -> str:
    return f"""
    <div class="col-6 col-sm-4 col-lg-2">
      <div class="kpi-card" style="--accent:{color}">
        <span class="kpi-icon">{icon}</span>
        <span class="kpi-label">{label}</span>
        <span class="kpi-value">{compact}</span>
        <span class="kpi-sub">{full}</span>
      </div>
    </div>"""

_CARD_HTML = """
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
body { margin:0; padding:0; background:transparent; }
.kpi-card {
    background: #1e1e2e;
    border-radius: 10px;
    padding: 16px 18px 14px;
    border-left: 4px solid var(--accent);
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-height: 95px;
    height: 100%;
}
.kpi-icon  { font-size: 1.2rem; line-height: 1; }
.kpi-label { font-size: 0.68rem; color: #9aa0b8; letter-spacing: .04em; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-value { font-size: 1.4rem; font-weight: 700; color: #f0f2ff; line-height: 1.1; white-space: nowrap; }
.kpi-sub   { font-size: 0.68rem; color: #6b7280; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
"""

def render_kpi_grid(grid_html: str, height: int = 220) -> None:
    html = f"""
    {_CARD_HTML}
    <div class="container-fluid p-0">
      <div class="row g-3">
        {grid_html}
      </div>
    </div>
    """
    components.html(html, height=height)

PLOTLY_MOBILE = dict(
    margin=dict(l=10, r=10, t=40, b=30),
    font=dict(size=11),
    legend=dict(orientation="h", y=-0.15, font=dict(size=10)),
)

def mobile_fig(fig, h=360):
    fig.update_layout(height=h, **PLOTLY_MOBILE)
    return fig

# ─── KPIs principales ─────────────────────────────────────────────────────────
tot_ventas   = df_activos["TOTAL"].sum()
tot_ganancia = df_activos["GANANCIA"].sum()
n_tickets    = len(df_activos)
n_cancelados = (df["ESTA_CANCELADO"] == "t").sum()
prom_ticket  = tot_ventas / n_tickets if n_tickets else 0
tot_articulos= df_l_act["CANTIDAD"].sum()
margen_gral  = (tot_ganancia / tot_ventas * 100) if tot_ventas else 0

cards_html = "".join([
    kpi_card("💰","Total vendido",    fmt_compact(tot_ventas),   f"${tot_ventas:,.2f}",   "#4f8ef7"),
    kpi_card("📈","Ganancia bruta",   fmt_compact(tot_ganancia), f"${tot_ganancia:,.2f}", "#22c55e"),
    kpi_card("🎯","Margen",           f"{margen_gral:.1f}%",     f"Ganancia / Ventas",    "#a78bfa"),
    kpi_card("🧾","Tickets",          fmt_compact_n(n_tickets),  f"{n_tickets:,} ventas", "#38bdf8"),
    kpi_card("📦","Artículos",        fmt_compact_n(tot_articulos),f"{tot_articulos:,.0f} uds","#fb923c"),
    kpi_card("💳","Ticket prom.",     fmt_compact(prom_ticket),  f"${prom_ticket:,.2f}",  "#f472b6"),
])
render_kpi_grid(cards_html)
st.divider()

# ─── Evolución de ventas ─────────────────────────────────────────────────────
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
fig_ts.add_trace(go.Bar(x=ts["VENDIDO_EN"], y=ts["TOTAL"], name="Total vendido", marker_color="#1f77b4", opacity=0.8), secondary_y=False)
fig_ts.add_trace(go.Bar(x=ts["VENDIDO_EN"], y=ts["GANANCIA"], name="Ganancia", marker_color="#2ca02c", opacity=0.6), secondary_y=False)
fig_ts.add_trace(go.Scatter(x=ts["VENDIDO_EN"], y=ts["TICKETS"], name="Nº tickets", mode="lines+markers", line=dict(color="#ff7f0e", width=2)), secondary_y=True)
fig_ts.update_layout(barmode="overlay", legend=dict(orientation="h", y=1.12))
fig_ts.update_yaxes(title_text="$ MXN", secondary_y=False)
fig_ts.update_yaxes(title_text="Tickets", secondary_y=True)
st.plotly_chart(mobile_fig(fig_ts, 380), width="stretch")

st.divider()

# ─── Patrones temporales ─────────────────────────────────────────────────────
st.subheader("🕐 Patrones temporales")

df_activos = df_activos.copy()
df_activos["HORA"] = df_activos["VENDIDO_EN"].dt.hour
df_activos["DIA_SEMANA_N"] = df_activos["VENDIDO_EN"].dt.dayofweek
DIAS = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
df_activos["DIA_SEMANA"] = df_activos["DIA_SEMANA_N"].map(dict(enumerate(DIAS)))

tab_hora, tab_dia = st.tabs(["Por hora", "Por día"])

with tab_hora:
    por_hora = df_activos.groupby("HORA").agg(TOTAL=("TOTAL","sum"), TICKETS=("ID","count")).reset_index()
    fig_h = px.bar(por_hora, x="HORA", y="TOTAL", color="TICKETS",
                   color_continuous_scale="Blues",
                   labels={"HORA":"Hora","TOTAL":"Venta ($)","TICKETS":"Tickets"},
                   title="Ventas por hora del día")
    st.plotly_chart(mobile_fig(fig_h, 340), width="stretch")

with tab_dia:
    por_dia = df_activos.groupby(["DIA_SEMANA_N","DIA_SEMANA"]).agg(TOTAL=("TOTAL","sum"), TICKETS=("ID","count")).reset_index().sort_values("DIA_SEMANA_N")
    fig_d = px.bar(por_dia, x="DIA_SEMANA", y="TOTAL", color="TICKETS",
                   color_continuous_scale="Oranges",
                   labels={"DIA_SEMANA":"Día","TOTAL":"Venta ($)","TICKETS":"Tickets"},
                   title="Ventas por día de la semana")
    st.plotly_chart(mobile_fig(fig_d, 340), width="stretch")

st.divider()

# ─── Productos más vendidos ──────────────────────────────────────────────────
st.subheader("🏆 Productos más vendidos")
top_n = st.slider("Top N productos", 5, 50, 15)

top_cant = (
    df_l_act.groupby("PRODUCTO_NOMBRE")
    .agg(CANTIDAD=("CANTIDAD","sum"), INGRESOS=("TOTAL_ARTICULO","sum"))
    .reset_index().sort_values("CANTIDAD", ascending=False).head(top_n)
)
top_ing = (
    df_l_act.groupby("PRODUCTO_NOMBRE")
    .agg(CANTIDAD=("CANTIDAD","sum"), INGRESOS=("TOTAL_ARTICULO","sum"))
    .reset_index().sort_values("INGRESOS", ascending=False).head(top_n)
)

tab_cant, tab_ing = st.tabs(["Por cantidad", "Por ingresos"])

with tab_cant:
    fig_tc = px.bar(top_cant.sort_values("CANTIDAD"), x="CANTIDAD", y="PRODUCTO_NOMBRE",
                    orientation="h", color="INGRESOS", color_continuous_scale="Viridis",
                    title=f"Top {top_n} por Cantidad",
                    labels={"CANTIDAD":"Unidades","PRODUCTO_NOMBRE":"","INGRESOS":"Ingresos $"})
    fig_tc.update_layout(coloraxis_showscale=False)
    st.plotly_chart(mobile_fig(fig_tc, max(350, top_n * 22)), width="stretch")

with tab_ing:
    fig_ti = px.bar(top_ing.sort_values("INGRESOS"), x="INGRESOS", y="PRODUCTO_NOMBRE",
                    orientation="h", color="CANTIDAD", color_continuous_scale="Plasma",
                    title=f"Top {top_n} por Ingresos ($)",
                    labels={"INGRESOS":"Ingresos $","PRODUCTO_NOMBRE":"","CANTIDAD":"Unidades"})
    fig_ti.update_layout(coloraxis_showscale=False)
    st.plotly_chart(mobile_fig(fig_ti, max(350, top_n * 22)), width="stretch")

st.divider()

# ─── Ventas por departamento ─────────────────────────────────────────────────
st.subheader("🗂️ Ventas por departamento")

depto = (
    df_l_act.groupby("DEPARTAMENTO")
    .agg(INGRESOS=("TOTAL_ARTICULO","sum"), CANTIDAD=("CANTIDAD","sum"), GANANCIA=("GANANCIA_TOTAL","sum"))
    .reset_index().sort_values("INGRESOS", ascending=False)
)
depto["MARGEN_%"] = (depto["GANANCIA"] / depto["INGRESOS"] * 100).round(1)

tab_dep_bar, tab_dep_pie = st.tabs(["Barras", "Distribución"])

with tab_dep_bar:
    fig_dep = px.bar(depto, x="INGRESOS", y="DEPARTAMENTO", orientation="h",
                     color="MARGEN_%", color_continuous_scale="RdYlGn",
                     hover_data=["CANTIDAD","GANANCIA","MARGEN_%"],
                     title="Ingresos por departamento (color = margen %)",
                     labels={"INGRESOS":"Ingresos $","DEPARTAMENTO":""})
    st.plotly_chart(mobile_fig(fig_dep, 500), width="stretch")

with tab_dep_pie:
    fig_pie = px.pie(depto, values="INGRESOS", names="DEPARTAMENTO",
                     title="Distribución de ingresos", hole=0.4)
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    fig_pie.update_layout(showlegend=False)
    st.plotly_chart(mobile_fig(fig_pie, 450), width="stretch")

st.divider()

# ─── Drill-down por departamento ─────────────────────────────────────────────
st.subheader("🔍 Detalle por departamento")

deptos_disponibles = sorted(df_l_act["DEPARTAMENTO"].dropna().unique().tolist())
depto_sel = st.selectbox(
    "Departamento",
    options=["— Todos —"] + deptos_disponibles,
    index=0,
    label_visibility="collapsed",
)

if depto_sel == "— Todos —":
    df_depto = df_l_act.copy()
    titulo_depto = "Todos los departamentos"
else:
    df_depto = df_l_act[df_l_act["DEPARTAMENTO"] == depto_sel].copy()
    titulo_depto = depto_sel

tot_d  = df_depto["TOTAL_ARTICULO"].sum()
gan_d  = df_depto["GANANCIA_TOTAL"].sum()
cant_d = df_depto["CANTIDAD"].sum()
prod_d = df_depto["PRODUCTO_NOMBRE"].nunique()
marg_d = (gan_d / tot_d * 100) if tot_d > 0 else 0

depto_cards = "".join([
    kpi_card("💰","Ingresos",      fmt_compact(tot_d),       f"${tot_d:,.2f}",      "#4f8ef7"),
    kpi_card("📈","Ganancia",      fmt_compact(gan_d),       f"${gan_d:,.2f}",       "#22c55e"),
    kpi_card("🎯","Margen",        f"{marg_d:.1f}%",         "Ganancia / Ingresos",  "#a78bfa"),
    kpi_card("📦","Unidades",      fmt_compact_n(cant_d),    f"{cant_d:,.0f} uds",   "#fb923c"),
    kpi_card("🏷️","Productos",     fmt_compact_n(prod_d),    f"{prod_d} únicos",     "#38bdf8"),
])
render_kpi_grid(depto_cards, height=200)

resumen_depto = (
    df_depto.groupby(["PRODUCTO_CODIGO", "PRODUCTO_NOMBRE"])
    .agg(CANTIDAD=("CANTIDAD","sum"), INGRESOS=("TOTAL_ARTICULO","sum"),
         GANANCIA=("GANANCIA_TOTAL","sum"), N_VENTAS=("TICKET_ID","nunique"))
    .reset_index()
)
resumen_depto = resumen_depto[resumen_depto["INGRESOS"] > 0].copy()
resumen_depto["MARGEN_%"] = (resumen_depto["GANANCIA"] / resumen_depto["INGRESOS"] * 100).round(1)
resumen_depto["INGRESOS"] = resumen_depto["INGRESOS"].round(2)
resumen_depto["GANANCIA"] = resumen_depto["GANANCIA"].round(2)
resumen_depto["CANTIDAD"] = resumen_depto["CANTIDAD"].round(2)

top_dep_n = st.slider("Top N en gráficas", 5, 30, 15, key="top_dep")

tab_di, tab_dg, tab_dm = st.tabs(["Ingreso", "Ganancia", "Margen %"])

with tab_di:
    top_ing_d = resumen_depto.nlargest(top_dep_n, "INGRESOS")
    fig_i = px.bar(top_ing_d.sort_values("INGRESOS"), x="INGRESOS", y="PRODUCTO_NOMBRE", orientation="h",
                   color="INGRESOS", color_continuous_scale="Blues",
                   title=f"Top {top_dep_n} — Mayor Ingreso ($)", labels={"INGRESOS":"$","PRODUCTO_NOMBRE":""})
    fig_i.update_layout(coloraxis_showscale=False)
    st.plotly_chart(mobile_fig(fig_i, max(380, top_dep_n * 24)), width="stretch")

with tab_dg:
    top_gan_d = resumen_depto.nlargest(top_dep_n, "GANANCIA")
    fig_g = px.bar(top_gan_d.sort_values("GANANCIA"), x="GANANCIA", y="PRODUCTO_NOMBRE", orientation="h",
                   color="GANANCIA", color_continuous_scale="Greens",
                   title=f"Top {top_dep_n} — Mayor Ganancia ($)", labels={"GANANCIA":"$","PRODUCTO_NOMBRE":""})
    fig_g.update_layout(coloraxis_showscale=False)
    st.plotly_chart(mobile_fig(fig_g, max(380, top_dep_n * 24)), width="stretch")

with tab_dm:
    top_marg_d = resumen_depto[resumen_depto["INGRESOS"] >= 500].nlargest(top_dep_n, "MARGEN_%")
    fig_m = px.bar(top_marg_d.sort_values("MARGEN_%"), x="MARGEN_%", y="PRODUCTO_NOMBRE", orientation="h",
                   color="MARGEN_%", color_continuous_scale="RdYlGn",
                   title=f"Top {top_dep_n} — Mayor Margen % (ingresos ≥ $500)",
                   labels={"MARGEN_%":"%","PRODUCTO_NOMBRE":""},
                   range_color=[0, max(top_marg_d["MARGEN_%"].max(), 1)] if not top_marg_d.empty else [0, 100])
    fig_m.update_layout(coloraxis_showscale=False)
    st.plotly_chart(mobile_fig(fig_m, max(380, top_dep_n * 24)), width="stretch")

with st.expander(f"📋 Tabla completa — {titulo_depto}", expanded=False):
    tabla_depto = resumen_depto.sort_values("INGRESOS", ascending=False).rename(columns={
        "PRODUCTO_CODIGO":"Código","PRODUCTO_NOMBRE":"Producto","CANTIDAD":"Unidades",
        "INGRESOS":"Ingresos $","GANANCIA":"Ganancia $","MARGEN_%":"Margen %","N_VENTAS":"# Ventas",
    })
    st.dataframe(
        tabla_depto[["Código","Producto","Unidades","Ingresos $","Ganancia $","Margen %","# Ventas"]],
        width="stretch", height=380,
    )
    csv_dep = tabla_depto.to_csv(index=False).encode("utf-8")
    nombre_csv = depto_sel.replace(" ", "_").replace("/", "-") if depto_sel != "— Todos —" else "todos"
    st.download_button(f"⬇️ Descargar — {titulo_depto}", csv_dep, f"productos_{nombre_csv}.csv", "text/csv", key="dl_depto")

st.divider()

# ─── Formas de pago ──────────────────────────────────────────────────────────
st.subheader("💳 Formas de pago")

forma_map = {"e": "Efectivo", "c": "Tarjeta/Crédito", "s": "Saldo/Otro"}
df_activos["FORMA_LABEL"] = df_activos["FORMA_PAGO"].str.strip().map(forma_map).fillna("Otro")

pago = df_activos.groupby("FORMA_LABEL").agg(TOTAL=("TOTAL","sum"), TICKETS=("ID","count")).reset_index()

tab_pago_m, tab_pago_t = st.tabs(["Por monto ($)", "Por tickets"])

with tab_pago_m:
    fig_pago1 = px.pie(pago, values="TOTAL", names="FORMA_LABEL",
                       title="Distribución por monto ($)", hole=0.4,
                       color_discrete_sequence=px.colors.qualitative.Set2)
    fig_pago1.update_traces(textinfo="percent+value+label")
    fig_pago1.update_layout(showlegend=False)
    st.plotly_chart(mobile_fig(fig_pago1, 340), width="stretch")

with tab_pago_t:
    fig_pago2 = px.pie(pago, values="TICKETS", names="FORMA_LABEL",
                       title="Distribución por tickets", hole=0.4,
                       color_discrete_sequence=px.colors.qualitative.Set2)
    fig_pago2.update_traces(textinfo="percent+value+label")
    fig_pago2.update_layout(showlegend=False)
    st.plotly_chart(mobile_fig(fig_pago2, 340), width="stretch")

st.divider()

# ─── Mapa de calor ───────────────────────────────────────────────────────────
st.subheader("🗓️ Mapa de calor: ventas por hora y día")

df_activos["DIA_SEMANA_LABEL"] = df_activos["DIA_SEMANA_N"].map(dict(enumerate(DIAS)))
heat = df_activos.groupby(["DIA_SEMANA_N","DIA_SEMANA_LABEL","HORA"]).agg(TOTAL=("TOTAL","sum")).reset_index()
heat_pivot = heat.pivot(index="DIA_SEMANA_N", columns="HORA", values="TOTAL").fillna(0)
heat_pivot.index = [DIAS[i] for i in heat_pivot.index]

fig_heat = px.imshow(heat_pivot, aspect="auto", color_continuous_scale="YlOrRd",
                     labels={"x":"Hora","y":"Día","color":"Ventas $"},
                     title="Ventas ($) por día y hora")
st.plotly_chart(mobile_fig(fig_heat, 320), width="stretch")

st.divider()

# ─── Margen por producto ─────────────────────────────────────────────────────
st.subheader("💰 Margen por producto (Top 30)")

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
                       title="Ingresos vs Margen (tamaño = cantidad)")
st.plotly_chart(mobile_fig(fig_marg, 400), width="stretch")

st.divider()

# ─── Tabla detallada ─────────────────────────────────────────────────────────
with st.expander("📋 Tabla detallada de productos", expanded=False):
    resumen_prod = (
        df_l_act.groupby(["PRODUCTO_CODIGO","PRODUCTO_NOMBRE","DEPARTAMENTO"])
        .agg(CANTIDAD=("CANTIDAD","sum"), INGRESOS=("TOTAL_ARTICULO","sum"),
             GANANCIA=("GANANCIA_TOTAL","sum"), N_VENTAS=("TICKET_ID","nunique"))
        .reset_index().sort_values("INGRESOS", ascending=False)
    )
    resumen_prod["MARGEN_%"] = (resumen_prod["GANANCIA"] / resumen_prod["INGRESOS"] * 100).where(resumen_prod["INGRESOS"] > 0).round(1)
    resumen_prod["INGRESOS"] = resumen_prod["INGRESOS"].round(2)
    resumen_prod["GANANCIA"] = resumen_prod["GANANCIA"].round(2)
    resumen_prod["CANTIDAD"] = resumen_prod["CANTIDAD"].round(2)

    st.dataframe(
        resumen_prod.rename(columns={
            "PRODUCTO_CODIGO":"Código","PRODUCTO_NOMBRE":"Producto","DEPARTAMENTO":"Departamento",
            "CANTIDAD":"Unidades","INGRESOS":"Ingresos $","GANANCIA":"Ganancia $","N_VENTAS":"# Ventas","MARGEN_%":"Margen %"
        }),
        width="stretch", height=400,
    )
    csv = resumen_prod.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar como CSV", csv, "productos_ventas.csv", "text/csv")

st.divider()

# ─── Costos y presión de margen ──────────────────────────────────────────────
df_prod_cat = run_query("SELECT CODIGO, DESCRIPCION, PCOSTO, PVENTA, DINVENTARIO FROM PRODUCTOS")
df_prod_cat["PCOSTO"] = pd.to_numeric(df_prod_cat["PCOSTO"], errors="coerce").fillna(0)
df_prod_cat["PVENTA"] = pd.to_numeric(df_prod_cat["PVENTA"], errors="coerce").fillna(0)
df_prod_cat = df_prod_cat.drop_duplicates(subset=["CODIGO"])

resumen_prod_costos = (
    df_l_act.groupby(["PRODUCTO_CODIGO","PRODUCTO_NOMBRE","DEPARTAMENTO"])
    .agg(CANTIDAD=("CANTIDAD","sum"), INGRESOS=("TOTAL_ARTICULO","sum"),
         GANANCIA=("GANANCIA_TOTAL","sum"), N_VENTAS=("TICKET_ID","nunique"))
    .reset_index().sort_values("INGRESOS", ascending=False)
)
resumen_prod_costos["MARGEN_%"] = (resumen_prod_costos["GANANCIA"] / resumen_prod_costos["INGRESOS"] * 100).where(resumen_prod_costos["INGRESOS"] > 0).round(1)
resumen_prod_costos["INGRESOS"] = resumen_prod_costos["INGRESOS"].round(2)
resumen_prod_costos["GANANCIA"] = resumen_prod_costos["GANANCIA"].round(2)
resumen_prod_costos["CANTIDAD"] = resumen_prod_costos["CANTIDAD"].round(2)

st.subheader("🧱 Costos y presión de margen")

costos = resumen_prod_costos.merge(
    df_prod_cat[["CODIGO", "PCOSTO", "PVENTA"]],
    left_on="PRODUCTO_CODIGO", right_on="CODIGO", how="left",
)
for c in ["PCOSTO","PVENTA","CANTIDAD","INGRESOS","GANANCIA"]:
    costos[c] = pd.to_numeric(costos[c], errors="coerce").fillna(0)
costos["MARGEN_%"] = pd.to_numeric(costos["MARGEN_%"], errors="coerce")

costos_validos = costos[costos["INGRESOS"] > 0].copy()

if costos_validos.empty:
    st.warning("No hay información suficiente de ventas para analizar costos.")
else:
    costos_validos["DEPARTAMENTO"] = costos_validos["DEPARTAMENTO"].fillna("Sin departamento")
    costos_validos["COSTO_COMPRA_TOTAL"] = costos_validos["PCOSTO"] * costos_validos["CANTIDAD"]
    costos_validos["COSTO_EST_UNIT"] = (
        (costos_validos["INGRESOS"] - costos_validos["GANANCIA"]) / costos_validos["CANTIDAD"]
    ).where(costos_validos["CANTIDAD"] > 0)

    umbral_ventas = costos_validos["CANTIDAD"].quantile(0.75)
    umbral_margen = costos_validos["MARGEN_%"].quantile(0.25)

    criticos = costos_validos[
        (costos_validos["CANTIDAD"] >= umbral_ventas) & (costos_validos["MARGEN_%"] <= umbral_margen)
    ].copy()

    if criticos.empty:
        criticos = costos_validos.sort_values(["CANTIDAD", "MARGEN_%"], ascending=[False, True]).head(15).copy()

    total_costo_compra = costos_validos["COSTO_COMPRA_TOTAL"].sum()
    costo_prom_unit = (total_costo_compra / costos_validos["CANTIDAD"].sum()) if costos_validos["CANTIDAD"].sum() > 0 else 0
    pct_ingresos_crit = (criticos["INGRESOS"].sum() / costos_validos["INGRESOS"].sum() * 100) if costos_validos["INGRESOS"].sum() > 0 else 0

    costos_cards = "".join([
        kpi_card("🛒","Costo compra", fmt_compact(total_costo_compra), f"${total_costo_compra:,.2f}", "#f59e0b"),
        kpi_card("📦","Costo prom/u", fmt_compact(costo_prom_unit), f"${costo_prom_unit:,.2f}", "#38bdf8"),
        kpi_card("⚠️","Críticos", fmt_compact_n(len(criticos)), "Alta venta + bajo margen", "#ef4444"),
        kpi_card("🎯","% en críticos", f"{pct_ingresos_crit:.1f}%", "Participación ingresos", "#a78bfa"),
    ])
    render_kpi_grid(costos_cards, height=200)

    costo_dep = (
        costos_validos.groupby("DEPARTAMENTO")
        .agg(UNIDADES=("CANTIDAD","sum"), INGRESOS=("INGRESOS","sum"), GANANCIA=("GANANCIA","sum"),
             COSTO_COMPRA_TOTAL=("COSTO_COMPRA_TOTAL","sum"), PRODUCTOS=("PRODUCTO_CODIGO","nunique"))
        .reset_index()
    )
    costo_dep["COSTO_COMPRA_PROM_UNIT"] = (costo_dep["COSTO_COMPRA_TOTAL"] / costo_dep["UNIDADES"]).where(costo_dep["UNIDADES"] > 0)
    costo_dep["MARGEN_%"] = (costo_dep["GANANCIA"] / costo_dep["INGRESOS"] * 100).where(costo_dep["INGRESOS"] > 0)
    costo_dep = costo_dep.sort_values("COSTO_COMPRA_PROM_UNIT", ascending=False)

    tab_costo_dep, tab_costo_criticos = st.tabs(["Costos por depto", "Productos críticos"])

    with tab_costo_dep:
        fig_dep_cost = px.bar(
            costo_dep.sort_values("COSTO_COMPRA_PROM_UNIT"), x="COSTO_COMPRA_PROM_UNIT", y="DEPARTAMENTO",
            orientation="h", color="MARGEN_%", color_continuous_scale="RdYlGn_r",
            title="Costo prom. unitario por departamento",
            labels={"COSTO_COMPRA_PROM_UNIT":"Costo unit $","DEPARTAMENTO":"","MARGEN_%":"Margen %"})
        st.plotly_chart(mobile_fig(fig_dep_cost, max(340, len(costo_dep) * 26)), width="stretch")

        with st.expander("📋 Tabla de costos por departamento"):
            tabla_dep = costo_dep.rename(columns={
                "DEPARTAMENTO":"Departamento","UNIDADES":"Unidades","INGRESOS":"Ingresos $",
                "GANANCIA":"Ganancia $","COSTO_COMPRA_TOTAL":"Costo total $",
                "COSTO_COMPRA_PROM_UNIT":"Costo unit $","MARGEN_%":"Margen %","PRODUCTOS":"# Productos",
            })
            for c in ["Unidades","Ingresos $","Ganancia $","Costo total $","Costo unit $"]:
                tabla_dep[c] = tabla_dep[c].round(2)
            tabla_dep["Margen %"] = tabla_dep["Margen %"].round(1)
            st.dataframe(tabla_dep[["Departamento","Costo unit $","Margen %","Unidades","Ingresos $","Ganancia $","Costo total $","# Productos"]],
                         width="stretch", height=min(420, 120 + len(tabla_dep) * 28))
            csv_dep_cost = tabla_dep.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Descargar CSV", csv_dep_cost, "costo_por_depto.csv", "text/csv", key="dl_costo_dep")

    with tab_costo_criticos:
        crit_plot = criticos.sort_values(["CANTIDAD","MARGEN_%"], ascending=[True, True]).tail(15)
        fig_crit = px.bar(crit_plot, x="CANTIDAD", y="PRODUCTO_NOMBRE", orientation="h",
                          color="MARGEN_%", color_continuous_scale="RdYlGn_r",
                          title="Top 15 — Alta venta con menor margen",
                          labels={"CANTIDAD":"Unidades","PRODUCTO_NOMBRE":"","MARGEN_%":"Margen %"})
        st.plotly_chart(mobile_fig(fig_crit, 420), width="stretch")

        with st.expander("📋 Tabla de productos críticos"):
            tabla_crit = (
                criticos[["PRODUCTO_CODIGO","PRODUCTO_NOMBRE","DEPARTAMENTO","CANTIDAD",
                          "INGRESOS","GANANCIA","MARGEN_%","PCOSTO","PVENTA","COSTO_EST_UNIT"]]
                .sort_values(["CANTIDAD","MARGEN_%"], ascending=[False, True])
                .rename(columns={
                    "PRODUCTO_CODIGO":"Código","PRODUCTO_NOMBRE":"Producto","DEPARTAMENTO":"Depto",
                    "CANTIDAD":"Uds","INGRESOS":"Ingresos $","GANANCIA":"Ganancia $","MARGEN_%":"Margen %",
                    "PCOSTO":"Costo unit $","PVENTA":"PVenta $","COSTO_EST_UNIT":"Costo est $"})
            )
            for c in ["Uds","Ingresos $","Ganancia $","Costo unit $","PVenta $","Costo est $"]:
                tabla_crit[c] = tabla_crit[c].round(2)
            tabla_crit["Margen %"] = tabla_crit["Margen %"].round(1)
            st.dataframe(tabla_crit, width="stretch", height=360)
            csv_crit = tabla_crit.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Descargar CSV", csv_crit, "productos_criticos.csv", "text/csv", key="dl_crit_margen")

st.divider()

# ─── Productos con costo $0 ─────────────────────────────────────────────────
with st.expander("⚠️ Productos con costo registrado en $0", expanded=False):
    st.caption("Productos cuyo PCOSTO = 0: toda la venta es ganancia contable.")

    codigos_cero = set(df_prod_cat[df_prod_cat["PCOSTO"] == 0]["CODIGO"].tolist())
    n_prods_catalogo = len(codigos_cero)
    df_cero = df_l_act[df_l_act["PRODUCTO_CODIGO"].isin(codigos_cero)].copy()

    if df_cero.empty:
        st.success("✅ No se encontraron ventas de productos con costo $0.")
    else:
        n_prods_vendidos = df_cero["PRODUCTO_NOMBRE"].nunique()
        total_rev_cero   = df_cero["TOTAL_ARTICULO"].sum()
        total_cant_cero  = df_cero["CANTIDAD"].sum()
        pct_ventas       = (total_rev_cero / tot_ventas * 100) if tot_ventas > 0 else 0

        cero_cards = "".join([
            kpi_card("⚠️","Catálogo $0", fmt_compact_n(n_prods_catalogo), f"{n_prods_catalogo} prods", "#ef4444"),
            kpi_card("📊","Vendidos", fmt_compact_n(n_prods_vendidos), f"de {n_prods_catalogo}", "#f97316"),
            kpi_card("💰","Ingresos", fmt_compact(total_rev_cero), f"${total_rev_cero:,.2f}", "#22c55e"),
            kpi_card("📈","% ventas", f"{pct_ventas:.1f}%", "Del período", "#a78bfa"),
        ])
        render_kpi_grid(cero_cards, height=200)

        resumen_cero = (
            df_cero.groupby(["PRODUCTO_CODIGO","PRODUCTO_NOMBRE"])
            .agg(CANTIDAD=("CANTIDAD","sum"), INGRESOS=("TOTAL_ARTICULO","sum"),
                 GANANCIA=("GANANCIA_TOTAL","sum"), N_VENTAS=("TICKET_ID","nunique"))
            .reset_index().sort_values("INGRESOS", ascending=False)
        )
        resumen_cero["MARGEN_%"] = (resumen_cero["GANANCIA"] / resumen_cero["INGRESOS"] * 100).where(resumen_cero["INGRESOS"] > 0).round(1)
        resumen_cero["INGRESOS"] = resumen_cero["INGRESOS"].round(2)
        resumen_cero["GANANCIA"] = resumen_cero["GANANCIA"].round(2)
        resumen_cero["CANTIDAD"] = resumen_cero["CANTIDAD"].round(2)

        st.dataframe(
            resumen_cero.rename(columns={
                "PRODUCTO_CODIGO":"Código","PRODUCTO_NOMBRE":"Producto","CANTIDAD":"Uds",
                "INGRESOS":"Ingresos $","GANANCIA":"Ganancia $","MARGEN_%":"Margen %","N_VENTAS":"# Ventas",
            })[["Código","Producto","Uds","Ingresos $","Ganancia $","Margen %","# Ventas"]],
            width="stretch", height=380,
        )
        csv_cero = resumen_cero.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Descargar CSV", csv_cero, "productos_costo_cero.csv", "text/csv", key="dl_cero")

# ─── Footer ──────────────────────────────────────────────────────────────────
st.caption(f"MI_BASE.sqlite | {datetime.now().strftime('%d/%m/%Y %H:%M')}")
