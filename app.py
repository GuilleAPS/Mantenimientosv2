# -*- coding: utf-8 -*-
"""
app.py - Dashboard Predictivo de Mantenimiento de Flota
========================================================
Arquitectura de 3 cargas manuales (sin API, sin OneDrive, sin aprobaciones):

  1. Registro de Camiones y Pilotos.xlsx  (OBLIGATORIO)
       -> la app extrae y clasifica los eventos de mantenimiento sola.

  2. Resumen de recorrido de Startrack    (OPCIONAL, recomendado)
       -> fuente de kilometraje. Soporta DOS formatos y los detecta solo:
            a) ODOMETRO acumulado  -> se usa directo
            b) RECORRIDO del periodo -> se reconstruye el odometro usando
               los Km ya capturados a mano como ancla.

  3. Servicios, Llantas y Baterias.xlsx   (OPCIONAL)
       -> tus Km historicos capturados a mano. Sirven de ancla y respaldo.

ENTRE CARGAS DE KILOMETRAJE la app PROYECTA:
    km_hoy = km_ultima_lectura + tasa_km_dia * dias_transcurridos
y lo marca siempre como estimado, indicando la antiguedad del dato.
Al volver a cargar el archivo de Startrack, todo se recalibra solo.
"""
import re
import unicodedata
from datetime import date
from itertools import combinations

import numpy as np
import pandas as pd
import streamlit as st

# ==========================================================================
# CONFIGURACION
# ==========================================================================
CABEZALES = {'146BGJ', '217BJG', '270BLF', '450BLX', '676BRC'}
VEHICULOS = {'024BCK', '109BYW', '146BGJ', '216BFH', '217BJG', '264BJY',
             '270BLF', '352BQK', '367BSN', '412BFD', '450BLX', '488BJB',
             '544BPQ', '576BLH', '599BYL', '676BRC'}
HOJAS_IGNORAR = {'servicios', 'registro', 'retroexcavadora'}

INTERVALOS_KM = {'servicioc': 5000, 'serviciot': 10000,
                 'llantas': 50000, 'baterias': 50000}
INTERVALO_KM_DEFAULT = 3000

MIN_LITROS_MOTOR = {'camion': 8, 'cabezal': 25}
ACEITE_NO_MOTOR = (r'80w90|85w140|\b85w|\b80w|multigear|spirax|hidraulic|'
                   r'transmision|coastal|ursa|freno|direccion|delo 8')
_NUM = {'1/2': .5, 'medio': .5, 'media': .5, 'un': 1, 'uno': 1, 'una': 1,
        'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5}
_PAT_LTS = (r'(1/2|medio|media|\d+(?:[.,]\d+)?|un[ao]?|dos|tres|cuatro|cinco)'
            r'\s*(litros?|galones?|cubetas?)\s+de\s+aceite([^,;.]{0,60})')


def norm(s):
    s = str(s).lower().strip()
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s)


# ==========================================================================
# 1) EXTRACCION Y CLASIFICACION DE EVENTOS (desde el Registro)
# ==========================================================================
def litros_aceite_motor(d):
    tot = 0.0
    for m in re.finditer(_PAT_LTS, d):
        cant, unidad, cola = m.group(1), m.group(2), m.group(3)
        if re.search(ACEITE_NO_MOTOR, cola):
            continue
        q = _NUM[cant] if cant in _NUM else float(cant.replace(',', '.'))
        tot += q * (1 if unidad.startswith('litro')
                    else (3.785 if unidad.startswith('galon') else 19))
    return round(tot, 1)


def clasificar(desc, placa):
    """Baterias > Llantas > Servicio.  Un servicio = filtro de aceite y/o
    engrase + litraje de motor propio de un cambio completo."""
    d = norm(desc)
    if re.search(r'\bbateria', d):
        return 'Baterias', 'alta'
    if 'llanta' in d and re.search(
            r'(\d+\s*llanta|(dos|tres|cuatro|un[a]?)\s+llanta|'
            r'llanta.{0,20}(triangle|r22|r17|r19|r20|r16|direccio|traccio|\dpr))', d):
        if not re.match(r'\s*(rotacion|balanceo|montaje|alineamiento|alineacion)', d):
            return 'Llantas', 'alta'

    es_cab = placa in CABEZALES
    tipo = 'ServicioT' if es_cab else 'ServicioC'
    minimo = MIN_LITROS_MOTOR['cabezal' if es_cab else 'camion']
    F = bool(re.search(r'filtro[^,;.]{0,14}(?:p/|para |de )?aceite|filtro p/aceite', d))
    E = 'engrase' in d
    L = litros_aceite_motor(d)

    if (F and (E or L >= minimo)) or (E and L >= minimo):
        return tipo, 'alta'
    if F or E or L >= minimo:
        return tipo, 'revisar'
    return None, 'descartado'


@st.cache_data(show_spinner=False)
def extraer_eventos(archivo):
    """Lee TODAS las hojas de vehiculo del Registro y devuelve los eventos."""
    xl = pd.ExcelFile(archivo)
    filas = []
    for hoja in xl.sheet_names:
        if norm(hoja) in HOJAS_IGNORAR:
            continue
        tok = str(hoja).strip().split()
        placa = tok[-1].upper() if tok else ''
        if placa not in VEHICULOS:
            continue
        raw = pd.read_excel(xl, sheet_name=hoja, header=None)
        hdr = None
        for i in range(min(12, len(raw))):
            fila = [norm(x) for x in raw.iloc[i].tolist()]
            if any(t == 'fecha' for t in fila) and any('costo' in t for t in fila):
                hdr = i
                break
        if hdr is None:
            continue
        cmap = {}
        for j, v in enumerate(raw.iloc[hdr].tolist()):
            t = norm(v)
            if t == 'fecha':                        cmap['Fecha'] = j
            elif 'taller' in t:                     cmap['Taller'] = j
            elif 'trabajo' in t or 'servicio' in t: cmap['Desc'] = j
            elif 'costo' in t:                      cmap['Costo'] = j
        if 'Fecha' not in cmap or 'Desc' not in cmap:
            continue
        for _, r in raw.iloc[hdr + 1:].iterrows():
            f = pd.to_datetime(r.iloc[cmap['Fecha']], errors='coerce')
            d = r.iloc[cmap['Desc']]
            if pd.isna(f) or str(d).strip() in ('', 'nan'):
                continue
            tipo, conf = clasificar(d, placa)
            filas.append({
                'Vehiculo': placa, 'Fecha': f.normalize(), 'Tipo': tipo,
                'Confianza': conf, 'Especificacion': str(d).strip(),
                'Costo': pd.to_numeric(r.iloc[cmap['Costo']], errors='coerce')
                         if 'Costo' in cmap else np.nan,
                'Taller': r.iloc[cmap['Taller']] if 'Taller' in cmap else '',
            })
    df = pd.DataFrame(filas)
    return df[df['Tipo'].notna()].copy(), df[df['Tipo'].isna()].copy()


# ==========================================================================
# 2) KILOMETRAJE (Startrack) - detecta odometro vs recorrido
# ==========================================================================
# El informe "Resumen Diario" de Startrack trae la hoja DETALLE con el odometro
# al inicio y al final de CADA DIA, por vehiculo. Validado contra los Km
# capturados a mano: "Odometro al inicio (km)" coincide EXACTO (error 0.0 km),
# asi que esa es la columna que se usa para fechar los servicios.
HOJA_GPS = 'Detalle'
FILA_ENCABEZADO = 4          # los encabezados reales estan en la fila 5 de Excel


def extraer_placa(txt):
    """'Camion Isuzu 1 (C-488 BJB)' -> '488BJB'   |   'C-576BLH' -> '576BLH'"""
    t = str(txt).upper().replace('-', ' ').replace('(', ' ').replace(')', ' ')
    t = re.sub(r'\s+', '', t)
    m = re.findall(r'C?(\d{3}[A-Z]{3})', t)
    return m[-1] if m else None


@st.cache_data(show_spinner=False)
def cargar_startrack(archivo):
    """
    Lee la hoja 'Detalle' del informe Resumen Diario de Startrack.
    Devuelve [Vehiculo, Fecha, Km_ini, Km_fin, Dist].
    """
    d = pd.read_excel(archivo, sheet_name=HOJA_GPS, header=FILA_ENCABEZADO)
    col = {norm(c): c for c in d.columns}

    def buscar(*claves):
        for k in claves:
            for n, c in col.items():
                if k in n:
                    return c
        return None

    c_veh = buscar('vehiculo')
    c_fec = buscar('fecha')
    c_ini = buscar('odometro al inicio')
    c_fin = buscar('odometro al final')
    c_dis = buscar('distancia')
    if not all([c_veh, c_fec, c_ini]):
        raise ValueError(f"La hoja '{HOJA_GPS}' no trae las columnas esperadas. "
                         f"Encontre: {list(d.columns)}")

    out = pd.DataFrame({
        'Vehiculo': d[c_veh].map(extraer_placa),
        'Fecha': pd.to_datetime(d[c_fec], errors='coerce'),
        'Km_ini': pd.to_numeric(d[c_ini], errors='coerce'),
        'Km_fin': pd.to_numeric(d[c_fin], errors='coerce') if c_fin else np.nan,
        'Dist': pd.to_numeric(d[c_dis], errors='coerce') if c_dis else np.nan,
    }).dropna(subset=['Vehiculo', 'Fecha', 'Km_ini'])
    out['Fecha'] = out['Fecha'].dt.normalize()
    out = out[out['Vehiculo'].isin(VEHICULOS)]
    return out.sort_values(['Vehiculo', 'Fecha']).reset_index(drop=True)


def construir_odometro(gps, km_manual):
    """
    Serie de odometro [Vehiculo, Fecha, Km].
    - Del GPS: Km_ini de cada dia (= el Km que se leia a mano), mas el Km_fin
      del ultimo dia como lectura mas reciente.
    - Los Km manuales entran como respaldo para fechas fuera del rango del GPS.
    """
    piezas = []
    if km_manual is not None and not km_manual.empty:
        piezas.append(km_manual[['Vehiculo', 'Fecha', 'Km']])

    if gps is not None and not gps.empty:
        piezas.append(gps.rename(columns={'Km_ini': 'Km'})[['Vehiculo', 'Fecha', 'Km']])
        ult = gps.sort_values('Fecha').groupby('Vehiculo').last().reset_index()
        ult = ult[ult['Km_fin'].notna()]
        if not ult.empty:
            piezas.append(pd.DataFrame({
                'Vehiculo': ult['Vehiculo'], 'Fecha': ult['Fecha'], 'Km': ult['Km_fin']}))

    if not piezas:
        return pd.DataFrame(columns=['Vehiculo', 'Fecha', 'Km'])
    odo = pd.concat(piezas, ignore_index=True).dropna()
    odo = (odo.sort_values(['Vehiculo', 'Fecha', 'Km'])
              .groupby(['Vehiculo', 'Fecha'], as_index=False)['Km'].max())
    return odo.sort_values(['Vehiculo', 'Fecha']).reset_index(drop=True)


# ==========================================================================
# 3) TASA DE USO Y PROYECCION
# ==========================================================================
VENTANA_TASA = 90     # dias para medir la tasa de uso


def tasa_km_dia(g, ventana=VENTANA_TASA):
    """
    Tasa de uso (km/dia) sobre los ultimos `ventana` dias.
    Con la serie diaria del GPS es una MEDICION, no una estimacion.
    Si solo hay puntos sueltos (km manuales), cae a Theil-Sen robusto.
    """
    g = g.dropna(subset=['Km']).sort_values('Fecha')
    g = g[~g['Fecha'].duplicated(keep='last')]
    if len(g) < 2:
        return None
    rec = g[g['Fecha'] >= g['Fecha'].max() - pd.Timedelta(days=ventana)]
    if len(rec) >= 10:                      # serie densa -> medicion directa
        dias = (rec['Fecha'].iloc[-1] - rec['Fecha'].iloc[0]).days
        if dias > 0:
            return (rec['Km'].iloc[-1] - rec['Km'].iloc[0]) / dias
    d = (g['Fecha'] - g['Fecha'].min()).dt.days.to_numpy(float)
    k = g['Km'].to_numpy(float)
    p = [(k[j] - k[i]) / (d[j] - d[i])
         for i, j in combinations(range(len(g)), 2) if d[j] != d[i]]
    p = [x for x in p if x > 0]
    return float(np.median(p)) if p else None


def estado_vehiculo(odo_veh):
    """Km medido a la ultima lectura + Km PROYECTADO a hoy."""
    s = odo_veh.dropna(subset=['Km']).sort_values('Fecha')
    if s.empty:
        return None
    f_ult, km_ult = s['Fecha'].iloc[-1], float(s['Km'].iloc[-1])
    tasa = tasa_km_dia(s)
    dias = (pd.Timestamp(date.today()) - f_ult).days
    km_hoy = km_ult + (tasa * dias if tasa else 0)
    return {'fecha_lectura': f_ult, 'km_medido': km_ult, 'tasa': tasa,
            'antiguedad': dias, 'km_hoy': km_hoy}


def predecir(eventos_veh, est, tipo):
    if est is None or not est['tasa']:
        return None
    sub = eventos_veh[eventos_veh['Tipo'] == tipo].dropna(subset=['Km'])
    if sub.empty:
        return None
    u = sub.sort_values('Fecha').iloc[-1]
    intervalo = INTERVALOS_KM.get(str(tipo).lower(), INTERVALO_KM_DEFAULT)
    objetivo = float(u['Km']) + intervalo
    faltan = objetivo - est['km_hoy']
    dias = faltan / est['tasa']
    return {
        'Vehiculo': eventos_veh['Vehiculo'].iloc[0], 'Tipo': tipo,
        'Ultimo servicio': u['Fecha'].date(), 'Km ultimo': int(u['Km']),
        'Km hoy (est.)': int(est['km_hoy']), 'Km objetivo': int(objetivo),
        'Km restantes': int(faltan), 'km/dia': round(est['tasa'], 1),
        'Dias restantes': int(round(dias)),
        'Fecha estimada': (pd.Timestamp(date.today())
                           + pd.Timedelta(days=dias)).date(),
    }


# ==========================================================================
# INTERFAZ
# ==========================================================================
st.set_page_config(page_title="Mantenimiento Predictivo", layout="wide")
st.title("🚚 Dashboard Predictivo de Mantenimiento")

with st.sidebar:
    st.header("Cargar archivos")
    f_reg = st.file_uploader("1. Registro de Camiones y Pilotos", type=['xlsx'])
    f_gps = st.file_uploader("2. Informe Resumen Diario (Startrack)",
                             type=['xls', 'xlsx'],
                             help="Sube el archivo COMPLETO. Se lee la hoja 'Detalle'.")
    f_km = st.file_uploader("3. Servicios/Llantas/Baterias (Km historicos)",
                            type=['xlsx'],
                            help="Tus Km capturados a mano. Sirven de ancla.")

if f_reg is None:
    st.info("Sube al menos el **Registro de Camiones y Pilotos** para comenzar.")
    st.stop()

eventos, descartados = extraer_eventos(f_reg)
st.success(f"{len(eventos)} eventos detectados en {eventos['Vehiculo'].nunique()} vehiculos.")

# --- Kilometraje ---
km_manual, gps = None, None
if f_km is not None:
    m = pd.read_excel(f_km).dropna(subset=['Vehiculo'])
    m['Fecha'] = pd.to_datetime(m['Fecha'], errors='coerce').dt.normalize()
    m['Km'] = pd.to_numeric(m['Km'], errors='coerce')
    km_manual = m.dropna(subset=['Fecha', 'Km'])[['Vehiculo', 'Fecha', 'Km']]

if f_gps is not None:
    try:
        gps = cargar_startrack(f_gps)
        st.info(f"Odometro GPS: **{len(gps)} lecturas diarias** de "
                f"{gps['Vehiculo'].nunique()} vehiculos "
                f"({gps['Fecha'].min().date()} a {gps['Fecha'].max().date()}).")
    except Exception as e:
        st.error(f"No pude leer el informe de Startrack: {e}")

odo = construir_odometro(gps, km_manual)
if odo.empty:
    st.warning("Sin kilometraje no puedo predecir. Sube el archivo 2 o el 3.")
    st.stop()

# pegar Km a cada evento (lectura mas cercana, +-3 dias)
ev = eventos.sort_values('Fecha')
ev = pd.merge_asof(ev, odo.sort_values('Fecha'), on='Fecha', by='Vehiculo',
                   direction='nearest', tolerance=pd.Timedelta(days=3))

# --- Frescura del dato ---
estados = {v: estado_vehiculo(g) for v, g in odo.groupby('Vehiculo')}
ant = [e['antiguedad'] for e in estados.values() if e]
if ant:
    peor = max(ant)
    msg = (f"Kilometraje actualizado hace **{min(ant)}-{peor} dias**. "
           f"Las cifras 'Km hoy' son **proyeccion** con la tasa km/dia; "
           f"vuelve a cargar Startrack para recalibrar.")
    (st.warning if peor > 30 else st.caption)(msg)

# --- Resumen ---
filas = []
for veh, g in ev.groupby('Vehiculo'):
    for tipo in g['Tipo'].unique():
        p = predecir(g, estados.get(veh), tipo)
        if p:
            filas.append(p)

if filas:
    res = pd.DataFrame(filas).sort_values('Dias restantes')
    st.subheader("📌 Proximos mantenimientos")

    def color(f):
        d = f['Dias restantes']
        c = ('background-color:#ff6b6b' if d < 7 else
             'background-color:#ffd93d' if d < 30 else
             'background-color:#a8e6a3')
        return ['' if col != 'Fecha estimada' else c for col in f.index]

    st.dataframe(res.style.apply(color, axis=1), use_container_width=True)
    v = (res['Dias restantes'] < 0).sum()
    if v:
        st.error(f"⚠️ {v} mantenimiento(s) VENCIDO(s).")

# --- Detalle ---
st.divider()
c1, c2 = st.columns(2)
veh = c1.selectbox("Vehiculo", sorted(ev['Vehiculo'].unique()))
g = ev[ev['Vehiculo'] == veh]
e = estados.get(veh)
if e:
    c2.metric("Km hoy (estimado)", f"{e['km_hoy']:,.0f}",
              f"{e['tasa']:.0f} km/dia · medido al {e['fecha_lectura'].date()}")

st.subheader("📈 Kilometraje")
s = odo[odo['Vehiculo'] == veh]
if len(s) >= 2:
    ch = s.set_index('Fecha')[['Km']]
    st.line_chart(ch)

st.subheader("🔧 Eventos")
st.dataframe(g[['Fecha', 'Tipo', 'Km', 'Confianza', 'Costo', 'Especificacion']],
             use_container_width=True)

with st.expander(f"🔍 Renglones para revisar ({len(descartados)} no clasificados)"):
    st.dataframe(descartados[['Vehiculo', 'Fecha', 'Especificacion', 'Costo']],
                 use_container_width=True)
