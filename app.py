pip install streamlit pandas numpy scikit-learn matplotlib streamlit-image-coordinates openpyxl

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st
from sklearn.linear_model import LinearRegression
from datetime import timedelta, date

# Configuración de la página
st.set_page_config(page_title="Dashboard Mantenimiento Predictivo", layout="wide", page_icon="🚚")

# --- ESTILOS CSS PERSONALIZADOS ---
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
    }
    .highlight-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNCIÓN PARA GENERAR SVG DEL CAMIÓN ---
def obtener_svg_camion(parte_seleccionada):
    """
    Genera un código SVG simple de un camión y resalta la parte seleccionada.
    Colores: Gris (#cccccc) para inactivo, Rojo (#ff4b4b) para activo.
    """
    # Colores por defecto
    c_llantas = "#555555"
    c_bateria = "#555555"
    c_motor = "#555555" # Para servicio completo/motor
    c_chasis = "#333333"
    
    # Lógica de resaltado
    parte = parte_seleccionada.lower().strip()
    if "llanta" in parte:
        c_llantas = "#ff4b4b" # Rojo vibrante
    elif "bateria" in parte or "batería" in parte:
        c_bateria = "#ff4b4b"
    elif "servicio" in parte or "motor" in parte:
        c_motor = "#ff4b4b"

    # SVG String (Dibujo vectorial simple)
    svg = f"""
    <svg width="100%" height="250" viewBox="0 0 600 300" xmlns="http://www.w3.org/2000/svg">
        <!-- Chasis y Remolque -->
        <rect x="50" y="50" width="350" height="150" fill="#dddddd" stroke="{c_chasis}" stroke-width="2"/>
        <rect x="400" y="80" width="120" height="120" fill="#999999" stroke="{c_chasis}" stroke-width="2"/>
        
        <!-- Ventana -->
        <rect x="460" y="90" width="50" height="50" fill="#aaddff" />
        
        <!-- Motor / Parrilla (Representa Servicio General) -->
        <rect x="520" y="140" width="10" height="60" fill="{c_motor}" rx="2" />
        <path d="M480 140 L520 140 L520 190 L480 190" fill="none" stroke="{c_motor}" stroke-width="3" stroke-dasharray="4"/>
        
        <!-- Batería (Caja lateral) -->
        <rect x="410" y="160" width="30" height="30" fill="{c_bateria}" stroke="black" stroke-width="1"/>
        <text x="415" y="180" font-family="Arial" font-size="10" fill="white">BAT</text>

        <!-- Llantas (Ruedas traseras del remolque) -->
        <circle cx="100" cy="200" r="30" fill="{c_llantas}" stroke="black" stroke-width="3"/>
        <circle cx="170" cy="200" r="30" fill="{c_llantas}" stroke="black" stroke-width="3"/>
        
        <!-- Llantas (Ruedas traseras del tracto) -->
        <circle cx="330" cy="200" r="30" fill="{c_llantas}" stroke="black" stroke-width="3"/>
        
        <!-- Llanta (Rueda delantera) -->
        <circle cx="480" cy="200" r="30" fill="{c_llantas}" stroke="black" stroke-width="3"/>
        
        <!-- Etiquetas visuales -->
        <text x="100" y="250" text-anchor="middle" font-family="Arial" font-size="12" fill="#333">Ejes Traseros</text>
        <text x="480" y="250" text-anchor="middle" font-family="Arial" font-size="12" fill="#333">Dirección</text>
    </svg>
    """
    return svg

# --- TÍTULO PRINCIPAL ---
st.title("📊 Dashboard Predictivo de Flota")
st.markdown("Control de predictivas, mantenimiento y visualización de estado.")

# 📤 Subir archivo
archivo = st.sidebar.file_uploader("📂 Cargar Excel de Mantenimiento", type=["xlsx"])

# --- LÓGICA PRINCIPAL ---
if archivo is not None:
    try:
        df = pd.read_excel(archivo)
        
        # Normalización de columnas para evitar errores de tipeo
        df.columns = df.columns.str.strip().str.capitalize() # Asegura 'Vehiculo', 'Tipo', 'Fecha', etc.
        
        # Verificar columnas necesarias
        columnas_necesarias = ['Vehiculo', 'Fecha', 'Km', 'Tipo']
        if not all(col in df.columns for col in columnas_necesarias):
            st.error(f"El archivo debe contener las columnas: {', '.join(columnas_necesarias)}")
            st.stop()

        df['Fecha'] = pd.to_datetime(df['Fecha'])
        df['Fecha_ordinal'] = df['Fecha'].map(pd.Timestamp.toordinal)

        vehiculos = df['Vehiculo'].unique()
        tipos_mantenimiento = df['Tipo'].unique()

        # 🔧 Intervalos personalizados (Normalizados a minúsculas para búsqueda)
        intervalos_km = { 
            "servicioc": 5000, 
            "serviciot": 10000, 
            "servicio general": 10000,
            "llantas": 50000, 
            "baterias": 50000,
            "batería": 50000
        }

        # ---------------------------------------------------------
        # 1. SECCIÓN DE VISUALIZACIÓN INTERACTIVA
        # ---------------------------------------------------------
        st.divider()
        col_viz, col_data = st.columns([1, 1])

        with col_viz:
            st.subheader("🚛 Inspección Visual")
            # Selección de Vehículo
            vehiculo_seleccionado = st.selectbox("Selecciona Unidad:", vehiculos)
            
            # Selección de Componente (Esto reemplaza tu selectbox simple anterior)
            st.write("**Selecciona el componente a inspeccionar:**")
            
            # Usamos radio horizontal para simular pestañas o botones
            tipo_seleccionado = st.radio(
                "Componente:",
                options=tipos_mantenimiento,
                horizontal=True,
                help="Selecciona una parte para ver su estado y predicción."
            )
            
            # Renderizar el SVG dinámico
            svg_html = obtener_svg_camion(tipo_seleccionado)
            st.markdown(svg_html, unsafe_allow_html=True)
            st.caption(f"Visualizando: **{tipo_seleccionado}** en unidad **{vehiculo_seleccionado}**")

        # ---------------------------------------------------------
        # 2. LÓGICA DE PREDICCIÓN (Corrección del Bug)
        # ---------------------------------------------------------
        with col_data:
            st.subheader("📉 Análisis Predictivo")
            
            # Filtrado de datos (AQUÍ ESTABA EL ERROR DE SINTAXIS)
            # Sintaxis correcta: df[(condicion1) & (condicion2)]
            sub_df = df[
                (df['Vehiculo'] == vehiculo_seleccionado) & 
                (df['Tipo'] == tipo_seleccionado)
            ].sort_values('Fecha').copy()

            if len(sub_df) < 2:
                st.warning("⚠️ Datos insuficientes para generar una predicción fiable (se necesitan al menos 2 registros históricos).")
                st.dataframe(sub_df)
            else:
                # Modelo de Regresión
                X = sub_df[['Fecha_ordinal']]
                y = sub_df['Km']
                modelo = LinearRegression().fit(X, y)
                sub_df['Km_predicho'] = modelo.predict(X)

                coef = modelo.coef_[0] # Km por día (velocidad de desgaste)
                
                if coef > 0:
                    ultimo = sub_df.iloc[-1]
                    tipo_norm = tipo_seleccionado.strip().lower()
                    km_int = intervalos_km.get(tipo_norm, 5000) # Default 5000 si no encuentra
                    
                    km_objetivo = ultimo['Km'] + km_int
                    fecha_ord_pred = (km_objetivo - modelo.intercept_) / coef
                    
                    if np.isfinite(fecha_ord_pred):
                        fecha_est = pd.Timestamp.fromordinal(int(fecha_ord_pred))
                        hoy = pd.Timestamp.now()
                        dias_restantes = (fecha_est - hoy).days
                        
                        # Tarjeta de Estado
                        color_estado = "green"
                        msg_estado = "Estado Óptimo"
                        if dias_restantes < 7:
                            color_estado = "red"
                            msg_estado = "⚠️ Mantenimiento Urgente"
                        elif dias_restantes < 30:
                            color_estado = "orange"
                            msg_estado = "⚠️ Planificar Mantenimiento"

                        st.markdown(f"""
                        <div class="highlight-card" style="border-left: 5px solid {color_estado};">
                            <h4>{msg_estado}</h4>
                            <p><strong>Próximo {tipo_seleccionado}:</strong> {fecha_est.date()} ({dias_restantes} días)</p>
                            <p><strong>Km Objetivo:</strong> {int(km_objetivo):,} km</p>
                            <p><strong>Uso diario prom:</strong> {int(coef)} km/día</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Gráfico
                        fig, ax = plt.subplots(figsize=(6, 3))
                        ax.plot(sub_df['Fecha'], sub_df['Km'], 'o-', label='Histórico', color='blue')
                        # Proyección futura simple
                        ax.plot([sub_df['Fecha'].iloc[-1], fecha_est], [sub_df['Km'].iloc[-1], km_objetivo], '--', color='red', label='Proyección')
                        
                        ax.set_title(f"Tendencia de Desgaste")
                        ax.grid(True, linestyle='--', alpha=0.6)
                        ax.legend()
                        st.pyplot(fig)
                    else:
                        st.error("Error matemático en la predicción.")
                else:
                    st.info("El vehículo no parece estar acumulando kilómetros (coeficiente 0 o negativo).")

        # ---------------------------------------------------------
        # 3. RESUMEN GLOBAL (Tabla inferior)
        # ---------------------------------------------------------
        st.divider()
        st.subheader("📋 Historial de Registros")
        st.dataframe(sub_df[['Fecha', 'Km', 'Tipo', 'Vehiculo']], use_container_width=True)

    except Exception as e:
        st.error(f"Ocurrió un error al procesar el archivo: {e}")
        st.write("Detalles técnicos:", e)

else:
    # Pantalla de bienvenida / Instrucciones
    st.info("👆 Por favor, sube tu archivo Excel en la barra lateral para comenzar.")
    
    st.markdown("""
    ### Formato requerido del Excel:
    El archivo debe tener las siguientes columnas (la primera fila como encabezado):
    - **Vehiculo**: Placa o ID del camión (ej. C-12345).
    - **Fecha**: Fecha del mantenimiento o registro de km.
    - **Km**: Kilometraje actual.
    - **Tipo**: 'Llantas', 'Baterias', 'ServicioC', etc.
    """)
