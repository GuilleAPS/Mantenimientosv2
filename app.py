import streamlit as st
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import datetime

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Mantenimiento Predictivo", layout="wide")

# --- FUNCIÓN: GENERAR SVG DEL CAMIÓN ---
def get_truck_svg(highlight_part):
    """
    Genera un código SVG de un camión.
    Cambia el color de partes específicas basado en el argumento 'highlight_part'.
    """
    # Colores base
    color_base = "#333333"  # Gris oscuro
    color_alert = "#FF0000" # Rojo brillante
    
    # Definir colores por defecto
    c_llantas = color_base
    c_bateria = color_base 
    c_general = color_base 
    
    # Lógica de coloreado
    if highlight_part == "Llantas":
        c_llantas = color_alert
    elif highlight_part == "Batería":
        c_bateria = color_alert
    elif highlight_part == "Parrilla/General":
        c_general = color_alert

    # OJO AQUÍ: La palabra 'svg_code' tiene 4 espacios antes (está indentada).
    # Pero el texto dentro de las comillas """ empieza pegado a la izquierda.
    svg_code=f"""
        <svg width="400" height="200" viewBox="0 0 400 200" xmlns="http://www.w3.org/2000/svg">
        <rect x="20" y="20" width="240" height="100" rx="5" fill="{c_general}" stroke="black" stroke-width="2"/>
        <path d="M260 120 L260 50 L300 50 L340 90 L340 120 Z" fill="{c_bateria}" stroke="black" stroke-width="2"/>
        <path d="M270 55 L300 55 L330 85 L270 85 Z" fill="#ADD8E6" stroke="black" stroke-width="1"/>
        <rect x="270" y="95" width="20" height="15" fill="{c_bateria}" stroke="white" stroke-width="1"/>
        <rect x="340" y="90" width="10" height="30" fill="{c_general}" stroke="black"/>
        <circle cx="60" cy="140" r="25" fill="{c_llantas}" stroke="black" stroke-width="3"/>
        <circle cx="120" cy="140" r="25" fill="{c_llantas}" stroke="black" stroke-width="3"/>
        <circle cx="300" cy="140" r="25" fill="{c_llantas}" stroke="black" stroke-width="3"/>
        <line x1="0" y1="165" x2="400" y2="165" stroke="#999" stroke-width="2"/> 
    </svg>"""
    
    return svg_code

# --- LÓGICA DE PREDICCIÓN ---
def predecir_mantenimiento(df_vehiculo, intervalo_km):
    # Validar datos suficientes
    if len(df_vehiculo) < 2:
        return None, "Se necesitan al menos 2 registros históricos para predecir."

    # Preparar datos para Scikit-Learn
    # X = Fecha (convertida a ordinal), y = Kilometraje
    df_vehiculo = df_vehiculo.sort_values('Fecha')

    # Convertimos fecha a ordinal para regresión lineal
    X = df_vehiculo['Fecha'].map(datetime.datetime.toordinal).values.reshape(-1, 1)
    y = df_vehiculo['Km'].values

    model = LinearRegression()
    model.fit(X, y)

    # Calcular cuándo alcanzará el próximo umbral
    ultimo_km = y[-1]
    proximo_mantenimiento_km = ultimo_km + intervalo_km

    # La ecuación es: Km = m * Fecha + b
    # Por tanto: Fecha = (Km - b) / m
    m = model.coef_[0]
    b = model.intercept_

    if m <= 0:
        return None, "Los datos no muestran un aumento de kilometraje (pendiente negativa o cero)."

    fecha_ordinal_predicha = (proximo_mantenimiento_km - b) / m
    fecha_predicha = datetime.datetime.fromordinal(int(fecha_ordinal_predicha))

    return fecha_predicha, proximo_mantenimiento_km

# --- INTERFAZ PRINCIPAL ---
st.title("🚛 Dashboard de Mantenimiento Predictivo")
st.markdown("Sube tu archivo Excel para analizar el estado de la flota.")

# 1. Carga de datos
uploaded_file = st.file_uploader("Cargar Excel (Columnas: Vehiculo, Fecha, Km, Tipo)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    # Preprocesamiento básico
    df['Fecha'] = pd.to_datetime(df['Fecha'])
    df['Km'] = pd.to_numeric(df['Km'], errors='coerce')

    # Limpieza de espacios en blanco en textos para evitar errores de filtrado
    if 'Tipo' in df.columns:
        df['Tipo'] = df['Tipo'].astype(str).str.strip()
    if 'Vehiculo' in df.columns:
        df['Vehiculo'] = df['Vehiculo'].astype(str).str.strip()

    # --- SIDEBAR: FILTROS ---
    st.sidebar.header("Configuración")

    # Selector de Vehículo
    lista_vehiculos = df['Vehiculo'].unique()
    vehiculo_seleccionado = st.sidebar.selectbox("Seleccionar Vehículo", lista_vehiculos)

    # Filtrar DF por vehículo primero (Lógica general del dashboard)
    df_vehiculo = df[df['Vehiculo'] == vehiculo_seleccionado].copy()

    # Selector de Tipo de Mantenimiento (Para el SVG y Umbrales)
    tipos_mantenimiento = ["Llantas", "Batería", "Parrilla/General"]
    seleccion_tipo = st.sidebar.selectbox("Analizar Componente", tipos_mantenimiento)

    # Definir intervalos según reglas del usuario
    intervalos = {
        "Llantas": 40000,
        "Batería": 30000,
        "Parrilla/General": 15000 # Valor ejemplo
    }
    intervalo_actual = intervalos.get(seleccion_tipo, 10000)

    # --- CORRECCIÓN SOLICITADA: FILTRADO ---
    # Nota: Para la predicción de KM usamos todo el historial del vehículo, 
    # pero si quisieras ver solo registros de ese tipo, aquí está la corrección:
    sub_df = df_vehiculo[df_vehiculo['Tipo'] == seleccion_tipo]

    # --- VISUALIZACIÓN SVG ---
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Visualización de Estado")
        # Renderizar SVG
        svg_html = get_truck_svg(seleccion_tipo)
        st.markdown(svg_html, unsafe_allow_html=True)
        st.info(f"Componente seleccionado: **{seleccion_tipo}**\n\nParte resaltada en rojo.")

    with col2:
        st.subheader(f"Predicción para: {vehiculo_seleccionado}")

        # Ejecutar Predicción con Sklearn
        fecha_est, km_target = predecir_mantenimiento(df_vehiculo, intervalo_actual)

        if fecha_est:
            st.success(f"📅 Fecha estimada de próximo cambio: **{fecha_est.strftime('%d-%m-%Y')}**")
            st.metric(label="Kilometraje Objetivo", value=f"{km_target:,.0f} km")
            st.metric(label="Intervalo Aplicado", value=f"{intervalo_actual:,.0f} km")

            # Gráfico simple de tendencia
            st.line_chart(df_vehiculo.set_index("Fecha")["Km"])
        else:
            st.warning(km_target) # Aquí km_target contiene el mensaje de error

    # Mostrar datos crudos
    st.write("### Historial de Registros")
    st.dataframe(df_vehiculo)

else:
    st.info("Esperando archivo Excel...")
    # Generar un Excel de ejemplo para que el usuario pruebe
    example_data = {
        'Vehiculo': ['Camion-01']*5,
        'Fecha': pd.date_range(start='2023-01-01', periods=5, freq='ME'),
        'Km': [10000, 12500, 15200, 17800, 20500],
        'Tipo': ['General', 'General', 'Llantas', 'General', 'Batería']
    }
    st.write("Estructura esperada del Excel (Ejemplo):")
    st.dataframe(pd.DataFrame(example_data))
