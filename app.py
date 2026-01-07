import streamlit as st
import os

st.title("🕵️‍♂️ Diagnóstico de Archivos")

# 1. ¿En qué carpeta estamos?
directorio_actual = os.getcwd()
st.write(f"📂 Carpeta actual del servidor: `{directorio_actual}`")

# 2. ¿Qué archivos ve el servidor aquí?
archivos = os.listdir(directorio_actual)
st.write("📄 Archivos detectados en esta carpeta:")
st.code(archivos)

# 3. ¿Existe requirements.txt y qué tiene adentro?
if "requirements.txt" in archivos:
    st.success("✅ El archivo requirements.txt EXISTE.")
    with open("requirements.txt", "r") as f:
        contenido = f.read()
        if contenido.strip():
            st.text("Contenido del archivo:")
            st.code(contenido)
        else:
            st.error("⚠️ El archivo existe pero está VACÍO.")
else:
    st.error("❌ El archivo requirements.txt NO ESTÁ en esta carpeta.")
    st.warning("El servidor no puede instalar nada si no encuentra este archivo aquí.")
