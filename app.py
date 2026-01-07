pip install streamlit pandas numpy scikit-learn matplotlib streamlit-image-coordinates openpyxl

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st
from sklearn.linear_model import LinearRegression
from datetime import timedelta, date
from streamlit_image_coordinates import streamlit_image_coordinates
from PIL import Image
import requests
from io import BytesIO

# --- CONFIGURACIÓN E INICIALIZACIÓN ---
st.set_page_config(
    page_title="Sistema de Mantenimiento Predictivo 4.0", 
    layout="wide",
    page_icon="🚛"
)

# Estilos CSS para mejorar la presentación visual
st.markdown("""
    <style>
  .stApp { background-color: #f0f2f6; }
    div.stButton > button:first-child {
        background-color: #2c3e50; color: white; border-radius: 5px;
    }
  .main-header {
        font-family: 'Helvetica', sans-serif; color: #1a237e; text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Dashboard Predictivo & Gemelo Digital de Flota")

# --- MÓDULO DE GESTIÓN DE ESTADO (SESSION STATE) ---
# Es vital inicializar variables para persistir la selección entre recargas
if 'filtro_parte' not in st.session_state:
    st.session_state['filtro_parte'] = None # Guardará 'llantas', 'motor', etc.
if 'vehiculo_activo' not in st.session_state:
    st.session_state['vehiculo_activo'] = None

# --- FUNCIONES DE LÓGICA DE NEGOCIO ---

def cargar_imagen_referencia():
    """
    Carga la imagen esquemática del camión.
    Usamos una URL estable de un diagrama vectorial para asegurar consistencia.
    """
    # URL de un icono plano de camión (vectorial/line art) adecuado para diagramas
    url_camion = "[https://cdn-icons-png.flaticon.com/512/2555/2555013.png](https://cdn-icons-png.flaticon.com/512/2555/2555013.png)"
    try:
        response = requests.get(url_camion)
        return Image.open(BytesIO(response.content))
    except Exception as e:
        st.error(f"Error cargando esquema visual: {e}")
        return None

def detectar_zona_clic(x, y, ancho_img, alto_img):
    """
    Mapea las coordenadas cartesianas (x,y) a una zona semántica del camión.
    Utiliza normalización (0.0 a 1.0) para ser independiente del tamaño de renderizado.
    """
    if x is None or y is None:
        return None
        
    # Normalizar coordenadas
    x_norm = x / ancho_img
    y_norm = y / alto_img
    
    # Definición de Bounding Boxes (Cajas delimitadoras)
    # Estas coordenadas deben calibrarse con la imagen específica usada.
    
    # Zona 1: Parte Frontal (Motor, Baterías, Aceite)
    # x: 0% a 35%, y: 20% a 80%
    if 0.0 <= x_norm <= 0.35:
        return "motor_sistema"
        
    # Zona 2: Parte Trasera Superior (Caja, Carrocería, Parrilla)
    # x: 35% a 100%, y: 0% a 60%
    elif 0.35 < x_norm <= 1.0 and 0.0 <= y_norm <= 0.60:
        return "carroceria_general"
        
    # Zona 3: Parte Inferior (Llantas, Rodamiento, Frenos)
    # x: 0% a 100%, y: 60% a 100%
    elif 0.0 <= x_norm <= 1.0 and 0.60 < y_norm <= 1.0:
        return "rodamiento"
        
    return "general"

def obtener_categorias_por_zona(zona):
    """
    Diccionario maestro que traduce Zonas Visuales a Tipos de Excel.
    """
    mapeo = {
        "motor_sistema": ["baterias", "motor", "aceite", "filtros", "servicioc", "serviciot"],
        "rodamiento": ["llantas", "alineacion", "frenos", "suspension", "rotacion"],
        "carroceria_general": ["parrilla", "pintura", "luces", "limpieza", "general"],
        "general": ["general", "varios", "otros"]
    }
    return mapeo.get(zona,)

# --- CARGA DE DATOS ---
archivo = st.file_uploader("📂 Sube tu archivo Excel de mantenimiento", type=["xlsx"])

if archivo is not None:
    try:
        df = pd.read_excel(archivo)
        
        # Preprocesamiento robusto
        df['Fecha'] = pd.to_datetime(df['Fecha'])
        df['Fecha_ordinal'] = df['Fecha'].map(pd.Timestamp.toordinal)
        # Normalización de texto para búsquedas insensibles a mayúsculas
        df = df.astype(str).str.strip().str.lower()
        # Convertir Km a numérico forzoso por si acaso
        df['Km'] = pd.to_numeric(df['Km'], errors='coerce').fillna(0)
        
        vehiculos = sorted(df['Vehiculo'].unique())
        tipos_mantenimiento = sorted(df.unique())
        
        # Base de conocimiento de intervalos (Configurable)
        intervalos_km = { 
            "servicioc": 5000, "serviciot": 10000, 
            "llantas": 50000, "baterias": 50000, "aceite": 5000 
        }

        # --- SECCIÓN SUPERIOR: SELECCIÓN DE ACTIVO ---
        col_sel, col_info = st.columns()
        with col_sel:
            st.subheader("1. Selección de Unidad")
            vehiculo_seleccionado = st.selectbox("Identificador de Camión", vehiculos)
            
            # Resetear filtro visual si cambia el vehículo
            if vehiculo_seleccionado!= st.session_state['vehiculo_activo']:
                st.session_state['vehiculo_activo'] = vehiculo_seleccionado
                st.session_state['filtro_parte'] = None
                st.rerun()

        # Filtrar DF por vehículo
        df_vehiculo = df[df['Vehiculo'] == vehiculo_seleccionado].sort_values('Fecha')

        # --- SECCIÓN CENTRAL: INTERFAZ VISUAL (GEMELO DIGITAL) ---
        st.markdown("---")
        st.subheader(f"2. Inspección Visual: {vehiculo_seleccionado}")
        
        col_visual, col_analisis = st.columns()
        
        with col_visual:
            st.info("👆 Haz clic en una parte del camión para filtrar el historial")
            imagen = cargar_imagen_referencia()
            
            if imagen:
                # Componente interactivo que captura el clic
                # key="click_data" mantiene el estado dentro del ciclo de Streamlit
                coords = streamlit_image_coordinates(
                    imagen,
                    width=400, # Ancho fijo para consistencia
                    key="click_data"
                )
                
                # Procesar clic
                if coords:
                    zona = detectar_zona_clic(
                        coords['x'], coords['y'], 
                        ancho_img=400, 
                        alto_img=imagen.height * (400 / imagen.width)
                    )
                    
                    if zona!= st.session_state['filtro_parte']:
                        st.session_state['filtro_parte'] = zona
                        st.rerun()
            
            # Indicador de estado del filtro
            zona_activa = st.session_state['filtro_parte']
            if zona_activa:
                st.success(f"Filtro Activo: **{zona_activa.upper().replace('_', ' ')}**")
                if st.button("🔄 Limpiar Filtro Visual"):
                    st.session_state['filtro_parte'] = None
                    st.rerun()
            else:
                st.info("Viendo: Todos los sistemas")

        # --- LÓGICA DE FILTRADO INTELIGENTE ---
        with col_analisis:
            # Determinar qué tipos mostrar en el selectbox
            tipos_filtrados = tipos_mantenimiento
            
            if zona_activa:
                keywords = obtener_categorias_por_zona(zona_activa)
                # Filtrar el DataFrame temporalmente para encontrar tipos que coincidan parcialmente
                if keywords:
                    mask = df_vehiculo.apply(lambda x: any(k in str(x) for k in keywords))
                    df_zona = df_vehiculo[mask]
                    
                    if not df_zona.empty:
                        tipos_filtrados = df_zona.unique()
                        st.caption(f"Mostrando mantenimientos relacionados con la zona seleccionada.")
                    else:
                        st.warning(f"No hay registros históricos para la zona {zona_activa} en este vehículo.")
                        tipos_filtrados =
                else:
                    tipos_filtrados =

            if len(tipos_filtrados) > 0:
                # Selector de Tipo (Ahora filtrado por la selección visual)
                tipo_seleccionado = st.selectbox(
                    "Sub-categoría de Mantenimiento", 
                    tipos_filtrados,
                    index=0
                )

                # --- ANÁLISIS PREDICTIVO (CORREGIDO) ---
                # Aquí estaba el error anterior. Se corrige la sintaxis de filtrado.
                sub_df = df_vehiculo == tipo_seleccionado].copy()

                if len(sub_df) < 2:
                    st.warning("⚠️ Datos insuficientes para generar una predicción fiable (mínimo 2 registros).")
                    st.dataframe(sub_df) # CORREGIDO: Quitados los corchetes extra
                else:
                    # Modelo Predictivo
                    X = sub_df[['Fecha_ordinal']]
                    y = sub_df['Km']
                    modelo = LinearRegression().fit(X, y)
                    
                    # Predicciones
                    sub_df['Km_predicho'] = modelo.predict(X)
                    coef = modelo.coef_ # Pendiente (Km por día)
                    intercept = modelo.intercept_
                    
                    # Visualización Gráfica
                    fig, ax = plt.subplots(figsize=(10, 4))
                    ax.scatter(sub_df['Fecha'], sub_df['Km'], color='#1f77b4', label='Datos Reales', zorder=5)
                    ax.plot(sub_df['Fecha'], sub_df['Km_predicho'], color='#ff7f0e', linestyle='--', label='Tendencia Lineal')
                    
                    # Cálculo de Próximo Evento
                    ultimo = sub_df.iloc[-1]
                    tipo_normalizado = str(tipo_seleccionado).strip().lower()
                    # Búsqueda difusa para el intervalo
                    km_intervalo = 5000 # Default
                    for k, v in intervalos_km.items():
                        if k in tipo_normalizado:
                            km_intervalo = v
                            break
                    
                    if coef > 0: # Solo predecir si el camión avanza
                        km_objetivo = ultimo['Km'] + km_intervalo
                        
                        # Evitar errores de fecha si la proyección es muy lejana
                        try:
                            fecha_objetivo_ordinal = (km_objetivo - intercept) / coef
                            fecha_estimada = date.fromordinal(int(fecha_objetivo_ordinal))
                            
                            # Añadir punto futuro al gráfico
                            ax.scatter([fecha_estimada], [km_objetivo], color='red', s=100, marker='*', label='Próximo Mantenimiento')
                            
                            # Tarjetas de Métricas (KPIs)
                            kpi1, kpi2, kpi3 = st.columns(3)
                            kpi1.metric("Último Kilometraje", f"{int(ultimo['Km']):,} km")
                            kpi2.metric("Intervalo Configurado", f"{km_intervalo:,} km")
                            
                            # Lógica de Semáforo para la Fecha
                            dias_hasta_evento = (fecha_estimada - date.today()).days
                            delta_color = "normal"
                            if dias_hasta_evento < 7: delta_color = "inverse" # Rojo/Alerta
                            
                            kpi3.metric("Fecha Estimada", f"{fecha_estimada}", f"{int(dias_hasta_evento)} días restantes", delta_color=delta_color)

                            st.markdown(f"**Análisis:** Basado en el uso actual ({coef:.1f} km/día), el componente **{tipo_seleccionado}** requerirá atención al llegar a **{int(km_objetivo):,} km**.")
                            
                        except (OverflowError, ValueError):
                            st.warning("La fecha proyectada es demasiado lejana para ser calculada.")
                    else:
                        st.warning("⚠️ Anomalía detectada: La tendencia de kilometraje es negativa o cero.")

                    ax.set_title(f"Evolución de Desgaste: {vehiculo_seleccionado} - {tipo_seleccionado}")
                    ax.set_xlabel("Fecha")
                    ax.set_ylabel("Kilometraje Acumulado")
                    ax.grid(True, alpha=0.3)
                    ax.legend()
                    st.pyplot(fig)
                    
                    with st.expander("Ver Datos Fuente y Descripciones Internas"):
                        st.dataframe(sub_df) # CORREGIDO: Quitados los corchetes extra
            else:
                st.info("Selecciona una zona válida o limpia el filtro para ver opciones.")

    except Exception as e:
        st.error(f"Error procesando el archivo: {str(e)}")
        st.info("Asegúrate de que el Excel tenga las columnas: Vehiculo, Fecha, Km, Tipo")
        
else:
    # Estado inicial (Landing Page)
    st.info("👋 Bienvenido al Sistema de Control de Predictivas.")
    st.markdown("""
    Para comenzar, sube el archivo Excel. El sistema generará automáticamente:
    1.  **Dashboard General:** Resumen de flota.
    2.  **Inspector Visual:** Haz clic en el diagrama del camión para filtrar por Llantas, Motor o Carrocería.
    3.  **Proyección:** Estimación de fechas basada en regresión lineal.
    """)
