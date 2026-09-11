# ------------------------------------------------------------------------------
# JUXALEGIS OS — OPERATING SYSTEM (PRODUCCIÓN DEFINITIVA UNIFICADA AL 100%)
# ARQUITECTURA: PYTHON + STREAMLIT + SQLITE (juxalegis_os.db)
# INTEGRACIÓN OFICIAL: SDK GOOGLE-GENAI (GEMINI FLASH / PRO + GROUNDING + MULTIMODAL)
# CONSOLIDACIÓN TOTAL: PARCHES 1 AL 16 + CORRECCIONES OPERATIVAS Y DE PERSONALIDAD
# ------------------------------------------------------------------------------

import os
import io
import re
import time
import base64
import sqlite3
import tempfile
from datetime import datetime
from PIL import Image

import streamlit as st
import streamlit.components.v1 as components

from google import genai
from google.genai import types

# ----------------- CONFIGURACIÓN BÁSICA & FAVICON CORPORATIVO -----------------
page_icon_target = (
    "logo_2.png" if os.path.exists("logo_2.png")
    else ("logo-os - juxalegis.jpg" if os.path.exists("logo-os - juxalegis.jpg")
    else ("logo.png" if os.path.exists("logo.png") else "⚖️"))
)

st.set_page_config(
    page_title="JUXALEGIS OS — Operating System",
    page_icon=page_icon_target,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------- DIRECTORIOS PERSISTENTES -----------------
CARPETA_BIBLIOTECA = "biblioteca_recursos"
os.makedirs(CARPETA_BIBLIOTECA, exist_ok=True)

# ----------------- BASE DE DATOS Y PERSISTENCIA PERMANENTE -----------------
DB_FILE = "juxalegis_os.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sesiones (
            session_id TEXT PRIMARY KEY,
            cuaderno TEXT DEFAULT 'General',
            titulo TEXT,
            ultima_actividad DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS cuadernos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS preferencias_usuario (
            email TEXT PRIMARY KEY,
            modo_operativo TEXT,
            nombre_ia TEXT,
            ultima_modificacion DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ----------------- HELPERS PERSISTENCIA Y SINCRONIZACIÓN -----------------
def crear_o_actualizar_sesion_db(session_id: str, primer_mensaje: str, cuaderno: str = "General") -> str:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    titulo_limpio = primer_mensaje.strip().replace("\n", " ")
    titulo_final = (titulo_limpio[:28] + "..") if len(titulo_limpio) > 28 else (titulo_limpio or "Nueva conversación")
    
    c.execute('''
        INSERT INTO sesiones (session_id, cuaderno, titulo, ultima_actividad)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id) DO UPDATE SET
            cuaderno = excluded.cuaderno,
            ultima_actividad = CURRENT_TIMESTAMP,
            titulo = CASE 
                WHEN sesiones.titulo IS NULL OR sesiones.titulo = 'Nueva conversación' 
                THEN ? 
                ELSE sesiones.titulo 
            END
    ''', (session_id, cuaderno, titulo_final, titulo_final))
    
    conn.commit()
    conn.close()
    return titulo_final

def guardar_mensaje_db(session_id: str, role: str, content: str, cuaderno: str = "General"):
    crear_o_actualizar_sesion_db(session_id, content if role == "user" else "Nueva conversación", cuaderno)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO chats (session_id, role, content) VALUES (?, ?, ?)', (session_id, role, content))
    conn.commit()
    conn.close()

def obtener_sesiones_recientes_db(cuaderno: str = "General", limite: int = 10):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT session_id, titulo, cuaderno, ultima_actividad 
        FROM sesiones 
        WHERE cuaderno = ? 
        ORDER BY ultima_actividad DESC 
        LIMIT ?
    """, (cuaderno, limite))
    filas = c.fetchall()
    conn.close()
    return [{"session_id": r[0], "titulo": r[1], "cuaderno": r[2], "timestamp": r[3]} for r in filas]

def cargar_mensajes_sesion(session_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT role, content FROM chats WHERE session_id = ? ORDER BY id ASC', (session_id,))
    filas = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in filas]

def obtener_nombre_ia_usuario(email: str) -> str:
    if not email:
        return "CHRONN"
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT nombre_ia FROM preferencias_usuario WHERE email = ?", (email.lower().strip(),))
    res = c.fetchone()
    conn.close()
    if res and res[0] and res[0].strip():
        return res[0].strip()
    return "CHRONN"

def guardar_nombre_ia_usuario(email: str, nombre_ia: str):
    if not email:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO preferencias_usuario (email, modo_operativo, nombre_ia, ultima_modificacion)
        VALUES (?, 'Asistente Integral', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(email) DO UPDATE SET
            nombre_ia = excluded.nombre_ia,
            ultima_modificacion = CURRENT_TIMESTAMP
    """, (email.lower().strip(), nombre_ia.strip()))
    conn.commit()
    conn.close()

def mover_hilo_a_cuaderno_db(session_id: str, nombre_cuaderno_destino: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "UPDATE sesiones SET cuaderno = ?, ultima_actividad = CURRENT_TIMESTAMP WHERE session_id = ?",
        (nombre_cuaderno_destino, session_id)
    )
    conn.commit()
    conn.close()

def crear_cuaderno_y_mover_hilo_db(session_id: str, nombre_nuevo_cuaderno: str):
    nombre_limpio = nombre_nuevo_cuaderno.strip()
    if not nombre_limpio:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO cuadernos (nombre) VALUES (?)", (nombre_limpio,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    c.execute(
        "UPDATE sesiones SET cuaderno = ?, ultima_actividad = CURRENT_TIMESTAMP WHERE session_id = ?",
        (nombre_limpio, session_id)
    )
    conn.commit()
    conn.close()

# ----------------- DIRECTRICES MAESTRAS: MODO ASISTENTE INTEGRAL -----------------
SYSTEM_INSTRUCTION_JUXALEGIS = """
INSTRUCTIVO DE CONFIGURACIÓN INTEGRAL DE SISTEMA (SYSTEM PROMPT / DIRECTRICES MAESTRAS)

I. NÚCLEO DE IDENTIDAD Y TRIPOLOGÍA DE ROLES INTEGRADOS
Operas bajo una tríada simbiótica indivisible, fusionando tres funciones de máxima jerarquía técnica bajo el rol unificado de ASISTENTE:

Rol 1: Abogado Consultor Senior y Colega de Litigio:
Especialista procesal y sustantivo en la Provincia de Córdoba y en las 24 jurisdicciones del país (fueros locales, Nacional y Federal). Conduces análisis dogmáticos, redactas piezas procesales complejas, elaboras convenios de honorarios y proyectas estrategias forenses con rigor absoluto.
Rol 2: Asistente Universal y Contenedor Estratégico:
Compañero analítico, apoyo operativo y guardián técnico. Tu cobertura temática no tiene fronteras: abarca desde la gestión ejecutiva cotidiana (mensajería, redacción a clientes, protocolos administrativos) hasta la resolución de problemas en cualquier área del conocimiento humano, técnico o científico. Cero complacencia: actúas como un filtro crítico que previene fallas, frena estrategias inviables y orienta con fundamentos sólidos.
Rol 3: Programador Senior y Arquitecto Tecnológico:
Experto en ciencias de la computación, desarrollo de software, arquitectura de sistemas, infraestructura, automatización y despliegue de modelos de Inteligencia Artificial. Dominas código limpio, depuración avanzada, lógica algorítmica y seguridad informática.

II. POLÍTICA DE COMUNICACIÓN Y REGLA DE NO COMPLACENCIA
Interacción con la profesional (colega/directora):
Trato de par técnico: directo, sincero, leal y de alta exigencia. Queda prohibida la condescendencia, la validación injustificada o las respuestas evasivas. Si un planteo fáctico, legal, técnico o de código carece de viabilidad, debes responder con un «NO» categórico, explicitando de inmediato los motivos normativos, lógicos o empíricos del rechazo y proponiendo la alternativa técnicamente admisible.
Interacción hacia clientes y terceros:
Tratamiento exclusivo de «usted», manteniendo absoluta formalidad, serenidad y distancia protocolar. Redacción clara, sobria y orientada a resguardar la posición del profesional y del estudio.
Veda léxica terminante:
Queda terminantemente prohibido utilizar los vocablos «blindar», «blindaje», «blindado» e «inobjetable», así como adjetivaciones absolutistas. En su lugar, debes emplear terminología técnica precisa: sólidamente fundado, resguardado, protegido, inimpugnable, jurídicamente viable, técnicamente robusto o ajustado a derecho.

III. DIRECTRICES PROCESALES, JUDICIALES Y ARANCELARIAS
Dominio procedimental Córdoba y jurisdicciones comparadas:
Conocimiento acabado del Código Procesal Civil y Comercial (Ley 8465), Código Procesal Penal (Ley 8123), Ley de Procedimiento Laboral (Ley 7987), Fuero de Familia, Contencioso-Administrativo, doctrina del Tribunal Superior de Justicia (TSJ) de Córdoba y jurisprudencia plenaria de Cámaras. Articulación homóloga para trámites federales y demás provincias.
Gestión operativa y plataformas:
Dominio completo del Sistema de Administración de Causas (SAC), Ciudadano Digital (CiDi), Portal de Aplicaciones Judiciales, Mediación Previa Obligatoria (Ley 10.543), Beneficio de Litigar sin Gastos, Registro General de la Propiedad (bloqueos, tracto abreviado, informes de inhibición/dominio) y Dirección General de Catastro (mensuras, subdivisiones, posesorios).
Regulación de honorarios y valor del Jus:
Para el cálculo de unidades arancelarias (Jus Córdoba - Ley 9459, UMA Federal - Ley 27.423 o equivalentes provinciales), debes consultar y contrastar siempre las escalas y liquidaciones oficiales actualizadas emitidas por los respectivos Colegios de Abogados y Poderes Judiciales. Redactas convenios de honorarios, pactos de cuotalitis y cartas de encomienda discriminando etapas, causales de rescisión, mora y costas.
Tolerancia cero a la alucinación de datos (Regla de Oro):
Prohibido inventar, deducir o autocompletar nombres, DNI, CUIT, CUIL, domicilios o nomenclaturas registrales. Todo dato debe provenir de manera unívoca y literal de los antecedentes provistos. Ante la mínima omisión, ilegibilidad o inconsistencia, debes frenar el acto y advertir el defecto antes de confeccionar cédulas, escritos o demandas.
Articulación interdisciplinaria:
Capacidad de análisis pericial transversal (medicina legal, accidentología, ingeniería, agrimensura, balances contables y auditorías de obra).

IV. DIRECTRICES DE ASISTENCIA UNIVERSAL Y OPERACIONES
Resolución ubicua de problemas:
Capacidad de estructurar soluciones paso a paso ante cualquier interrogante técnico, operativo o conceptual, sin importar su escala o disciplina (gestión de recursos, procedimientos operativos estándar, ciencias duras o vida práctica).
Gestión ejecutiva de clientes:
Elaboración de respuestas para recepción de casos, filtrado y priorización de mensajes, confección de minutas explicativas para legos, estructuración de acuerdos y cronogramas de seguimiento de tareas.
Estudios de viabilidad integral:
Evaluación previa e implacable de viabilidad: legitimación, competencia, caducidad/prescripción, pertinencia probatoria, relación costo/beneficio y riesgos procesales o de ejecución.

V. DIRECTRICES DE PROGRAMACIÓN E INTELIGENCIA ARTIFICIAL
Desarrollo y código de producción:
Generación de código robusto, modular, documentado y seguro en lenguajes de propósito general y web (Python, JavaScript/TypeScript, SQL, HTML/CSS, entre otros).
Implementación de Inteligencia Artificial:
Dominio de prompts avanzados, integración de APIs de LLMs, automatizaciones mediante scripts, vectorización, arquitecturas RAG, gestión de bases de datos y desarrollo de interfaces (ej. Streamlit, dashboards o apps web).
Auditoría y refactorización:
Diagnóstico de errores sintácticos o de lógica, resolución de dependencias, auditoría de vulnerabilidades y optimización de rendimiento de aplicaciones y plataformas web.
"""

# ----------------- ESTILOS GLOBALES, IDENTIDAD & TIPOGRAFÍAS -----------------
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700&display=swap');

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 7rem;
        padding-left: 1.2rem;
        padding-right: 1.2rem;
    }

    .stApp {
        background-color: #1B2226;
        color: #E1E6EB;
        font-family: 'Segoe UI', sans-serif;
    }
    .stSidebar {
        background-color: #161B1E;
    }
    h1, h2, h3, .cinzel-title {
        color: #DCA48A !important;
        font-family: 'Cinzel', serif !important;
        letter-spacing: 1px;
    }

    /* SUPRESIÓN TOTAL Y ESTRICTA DE AVATARES */
    [data-testid="stChatMessageAvatarUser"],
    [data-testid="stChatMessageAvatarAssistant"],
    [data-testid="stChatMessage"] div:first-child:has(svg),
    [data-testid="stChatMessage"] div:first-child:has(img),
    [data-testid="stChatMessage"] div:first-child:has([data-testid="stIconMaterial"]),
    [data-testid="stChatMessage"] > div:first-child:not(:only-child) {
        display: none !important;
        width: 0 !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    div[data-testid="stChatMessage"] {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        gap: 0 !important;
    }

    /* Botón general */
    .stButton>button {
        background-color: #242D33;
        color: #E1E6EB;
        border: 1px solid #DCA48A;
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        background-color: #DCA48A !important;
        color: #1B2226 !important;
        border-color: #DCA48A !important;
    }

    /* Botón Iniciar Sesión con Hover Rosa Oro */
    div[data-testid="stForm"] button,
    .stButton > button[kind="primary"] {
        background-color: #161b1e !important;
        color: #d1d5db !important;
        border: 1px solid #3c4043 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    div[data-testid="stForm"] button:hover,
    .stButton > button[kind="primary"]:hover {
        background-color: rgba(220, 164, 138, 0.12) !important;
        border-color: #DCA48A !important;
        color: #DCA48A !important;
        box-shadow: 0 0 14px rgba(220, 164, 138, 0.28) !important;
        transform: translateY(-1px) !important;
    }
    div[data-testid="stForm"] button:active,
    div[data-testid="stForm"] button:focus:not(:active) {
        background-color: #DCA48A !important;
        border-color: #DCA48A !important;
        color: #1B2226 !important;
        box-shadow: 0 0 18px rgba(220, 164, 138, 0.45) !important;
    }

    /* Popovers estilo sistema */
    div[data-testid="stPopoverBody"] {
        background-color: #1e1f20 !important;
        border: 1px solid #3c4043 !important;
        border-radius: 16px !important;
        padding: 10px 8px !important;
        box-shadow: 0 8px 28px rgba(0, 0, 0, 0.6) !important;
    }
    div[data-testid="stPopoverBody"] button {
        background: transparent !important;
        color: #e3e3e3 !important;
        border: none !important;
        text-align: left !important;
        justify-content: flex-start !important;
        border-radius: 8px !important;
        padding: 8px 12px !important;
        width: 100% !important;
        font-size: 14px !important;
    }
    div[data-testid="stPopoverBody"] button:hover {
        background-color: #2d2f31 !important;
        color: #ffffff !important;
    }

    /* Botón circular '+' */
    .btn-plus-container div[data-testid="stPopover"] > button {
        background-color: #1e1f20 !important;
        color: #e3e3e3 !important;
        border: 1px solid #3c4043 !important;
        border-radius: 50% !important;
        width: 44px !important;
        height: 44px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
        font-size: 24px !important;
        line-height: 1 !important;
        transition: all 0.2s ease-in-out !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3) !important;
    }
    .btn-plus-container div[data-testid="stPopover"] > button:hover {
        background-color: #2d2f31 !important;
        border-color: #DCA48A !important;
        color: #DCA48A !important;
        transform: scale(1.04);
    }

    /* Pastilla central auto-expandible */
    div[data-testid="stTextArea"] textarea {
        background-color: #1e1f20 !important;
        color: #ffffff !important;
        border: 1px solid #3c4043 !important;
        border-radius: 16px !important;
        padding: 12px 16px !important;
        font-size: 15px !important;
        line-height: 1.5 !important;
        resize: vertical !important;
        min-height: 48px !important;
        max-height: 280px !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    div[data-testid="stTextArea"] textarea:focus {
        border-color: #DCA48A !important;
        box-shadow: 0 0 0 2px rgba(220, 164, 138, 0.25) !important;
    }

    /* Botones de acción derecha */
    .btn-accion-redonda {
        background-color: #1e1f20 !important;
        border: 1px solid #3c4043 !important;
        color: #e3e3e3 !important;
        border-radius: 50% !important;
        width: 44px !important;
        height: 44px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 18px;
    }
    .btn-accion-redonda:hover {
        border-color: #DCA48A !important;
        color: #DCA48A !important;
        transform: scale(1.05);
    }

    div[data-testid="stSelectbox"] div[data-baseweb="select"] {
        border-radius: 14px !important;
        background-color: #1e1f20 !important;
        border: 1px solid #3c4043 !important;
        font-size: 13px !important;
        color: #DCA48A !important;
    }

    .gemini-menu-divider {
        border-top: 1px solid #3c4043;
        margin: 6px 4px;
    }

    .badge-beta {
        background-color: #27272a;
        color: #a5b4fc;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: bold;
        border: 1px solid #4338ca;
    }
    .user-footer {
        display: flex;
        align-items: center;
        gap: 10px;
        padding-top: 15px;
        border-top: 1px solid #27272a;
        margin-top: 20px;
    }
    .user-avatar {
        width: 38px !important;
        height: 38px !important;
        border-radius: 50% !important;
        background: #DCA48A !important;
        border: 2px solid #DCA48A !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-weight: 800 !important;
        color: #1B2226 !important;
        font-size: 0.85rem !important;
    }
    .active-chat-pill button {
        background-color: rgba(220, 164, 138, 0.18) !important;
        border: 1px solid #DCA48A !important;
        color: #DCA48A !important;
        font-weight: 700 !important;
    }
    .notebook-card-gold-unified {
        background: #DCA48A !important;
        border-radius: 10px !important;
        padding: 14px 16px !important;
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35) !important;
        margin-bottom: 12px !important;
    }
    .notebook-card-title-sm {
        font-family: 'Cinzel', serif !important;
        font-size: 0.92rem !important;
        font-weight: 700 !important;
        color: #161B1E !important;
        margin: 0 !important;
    }
    .notebook-card-meta-sm {
        font-size: 0.72rem !important;
        color: #2E3840 !important;
        font-weight: 600 !important;
        margin-top: 4px !important;
    }
    .module-header-serif {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 0.95rem !important;
        font-weight: 600 !important;
        color: #DCA48A !important;
        letter-spacing: 1.5px !important;
        text-transform: uppercase !important;
        border-bottom: 1px solid rgba(220, 164, 138, 0.25);
        padding-bottom: 5px;
        margin-bottom: 14px;
    }
    .expediente-title-serif {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 1.25rem !important;
        font-weight: 600 !important;
        color: #DCA48A !important;
        letter-spacing: 1.2px !important;
        text-transform: uppercase !important;
    }

    /* ESTILOS TIMES NEW ROMAN (SALUDO Y SIDEBAR) */
    .saludo-bienvenida-times {
        font-family: 'Times New Roman', Times, Georgia, serif !important;
        font-size: 2.35rem !important;
        font-weight: 400 !important;
        color: #FFF9E6 !important;
        letter-spacing: 0.2px !important;
        margin: 0 !important;
        line-height: 1.3 !important;
        text-align: center !important;
        text-transform: none !important;
    }
    .saludo-usuario-rosaoro {
        font-family: 'Times New Roman', Times, Georgia, serif !important;
        color: #DCA48A !important;
        font-weight: 700 !important;
        letter-spacing: 0.4px !important;
    }
    .sidebar-config-times-title {
        font-family: 'Times New Roman', Times, Georgia, serif !important;
        font-size: 0.95rem !important;
        font-weight: 700 !important;
        color: #DCA48A !important;
        letter-spacing: 1.5px !important;
        text-transform: uppercase !important;
        margin-top: 14px !important;
        margin-bottom: 8px !important;
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
    }
    </style>
""", unsafe_allow_html=True)

# ----------------- GESTIÓN DE API KEY GOOGLE GEMINI -----------------
def obtener_gemini_api_key():
    try:
        if "GEMINI_API_KEY" in st.secrets:
            val = st.secrets["GEMINI_API_KEY"]
            if val:
                return "".join(str(val).split()).strip('"').strip("'")
    except Exception:
        pass
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return "".join(str(env_key).split()).strip('"').strip("'")
    return None

GEMINI_API_KEY = obtener_gemini_api_key()

CORREOS_AUTORIZADOS = [
    "gail@juxalegis.com",
    "dra.martin@juxalegis.com",
    "dr.campos@juxalegis.com"
]

def obtener_imagen_base64(ruta_archivo):
    if os.path.exists(ruta_archivo):
        with open(ruta_archivo, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    return None

def procesar_documento_pesado(client: genai.Client, archivo_subido):
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{archivo_subido.name}") as tmp_file:
        tmp_file.write(archivo_subido.getvalue())
        ruta_temporal = tmp_file.name
    try:
        documento_en_nube = client.files.upload(
            file=ruta_temporal,
            config=types.UploadFileConfig(display_name=archivo_subido.name)
        )
    finally:
        if os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)
    return documento_en_nube

# ----------------- MÓDULOS MULTIMEDIA (IMAGEN 3 / VEO) -----------------
def generar_imagen_institucional(client, prompt_usuario, relacion_aspecto="1:1"):
    try:
        with st.spinner("Generando composición visual con Imagen 3..."):
            resultado = client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=f"Professional corporate context, clean aesthetic: {prompt_usuario}",
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio=relacion_aspecto,
                    output_mime_type="image/jpeg"
                )
            )
            for img_gen in resultado.generated_images:
                return Image.open(io.BytesIO(img_gen.image.image_bytes))
    except Exception as error:
        st.error(f"Inconveniente en generación de imagen: {error}")
        return None

def generar_video_institucional(client, prompt_guion):
    try:
        with st.spinner("Procesando síntesis de video con Veo... Esto puede demorar unos instantes."):
            operacion = client.models.generate_videos(
                model="veo-2.0-generate-001",
                prompt=f"High quality cinematic corporate footage: {prompt_guion}",
                config=types.GenerateVideosConfig(aspect_ratio="16:9")
            )
            while not operacion.done:
                time.sleep(8)
                operacion = client.operations.get(operacion)
            return operacion.result.generated_videos[0].video.video_bytes
    except Exception as error:
        st.error(f"Inconveniente en generación audiovisual: {error}")
        return None

# ----------------- PROTOCOLO, GÉNERO Y PERSONALIDAD ASISTENCIAL -----------------
def obtener_tratamiento_usuario(email_usuario: str) -> dict:
    mail = email_usuario.lower().strip()
    if "martin" in mail:
        return {
            "vocativo": "Estimada Dra. Martín",
            "genero": "femenino",
            "pronombre_objeto": "asistirla"
        }
    elif "campos" in mail:
        return {
            "vocativo": "Estimado Dr. Campos",
            "genero": "masculino",
            "pronombre_objeto": "asistirlo"
        }
    elif "gail" in mail:
        return {
            "vocativo": "Estimada Gail",
            "genero": "femenino",
            "pronombre_objeto": "asistirla"
        }
    else:
        nombre_base = mail.split('@')[0].replace('.', ' ').title()
        return {
            "vocativo": f"Estimado/a {nombre_base}",
            "genero": "neutro",
            "pronombre_objeto": "asistirle"
        }

def renderizar_bienvenida_calibrada(user_name_raw, alias_display, act_cuad, perfil_voz):
    datos_traspaso = obtener_tratamiento_usuario(st.session_state.get("usuario_email", ""))
    vocativo_destacado = datos_traspaso["vocativo"]
    pronombre = datos_traspaso["pronombre_objeto"]

    st.markdown(f"""
        <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 38vh; text-align: center; gap: 20px;">
            <h1 class="saludo-bienvenida-times">
                {vocativo_destacado}, ¿en qué puedo {pronombre} hoy?
            </h1>
            <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
                <span style="background-color: #242D33; color: #DCA48A; border: 1px solid rgba(220, 164, 138, 0.4); border-radius: 9999px; padding: 4px 12px; font-size: 0.75rem; font-weight: 600;">⚙️ ASISTENTE INTEGRAL</span>
                <span style="background-color: #242D33; color: #DCA48A; border: 1px solid rgba(220, 164, 138, 0.4); border-radius: 9999px; padding: 4px 12px; font-size: 0.75rem; font-weight: 600;">🧠 {alias_display}</span>
                <span style="background-color: #242D33; color: #DCA48A; border: 1px solid rgba(220, 164, 138, 0.4); border-radius: 9999px; padding: 4px 12px; font-size: 0.75rem; font-weight: 600;">📁 {act_cuad.upper()}</span>
                <span style="background-color: #242D33; color: #DCA48A; border: 1px solid rgba(220, 164, 138, 0.4); border-radius: 9999px; padding: 4px 12px; font-size: 0.75rem; font-weight: 600;">🎙️ {perfil_voz.upper()}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

def construir_system_prompt_personalizado(act_cuad_save: str, alias_display: str, perfil_voz_activa: str) -> str:
    datos_usr = obtener_tratamiento_usuario(st.session_state.get("usuario_email", ""))
    genero_usuario = datos_usr["genero"]
    vocativo_oficial = datos_usr["vocativo"]

    if perfil_voz_activa == "mujer":
        autopercepcion_ia = (
            f"Tu identidad operativa es femenina bajo el nombre {alias_display}. "
            f"Debes autopercibirte y redactar en primera persona femenina (ej: 'estoy preparada', 'quedo atenta', 'comprometida')."
        )
    else:
        autopercepcion_ia = (
            f"Tu identidad operativa es masculina bajo el nombre {alias_display}. "
            f"Debes autopercibirte y redactar en primera persona masculina (ej: 'estoy preparado', 'quedo atento', 'comprometido')."
        )

    adicional_conducta = f"""
VI. PROTOCOLO DE IDENTIDAD, TRATAMIENTO Y ASERTIVIDAD INMEDIATA

1. Concordancia de Interlocutor:
Estás interactuando con: {vocativo_oficial} (género {genero_usuario}).
Dirígete siempre respetando rigurosamente su género y rango formal. Si es mujer: «Estimada Dra. Martín», «doctora», o fórmulas análogas concordadas en femenino. Si es varón: «Estimado Dr. Campos», «doctor», etc.

2. Autopercepción de la IA:
{autopercepcion_ia}

3. Estructura Obligatoria de Respuesta (Regla de Asertividad Binaria):
Ante toda consulta, planteo, viabilidad, duda técnica, procesal o de código formulada por tu colega/directora:
- LA PRIMERA PALABRA DE TU RESPUESTA DEBE SER TAJANTE Y CATEGÓRICA: «SÍ.» o «NO.».
- Quedan prohibidas las introducciones tibias, dubitativas o evasivas (como «En principio dependerá...», «Es relativo...», «Podría ser...»).
- Inmediatamente después de fijar el «SÍ.» o «NO.», desarrolla en párrafos ordenados el fundamento dogmático, normativo, jurisprudencial o técnico que sustenta esa postura (el porqué sí o el porqué no).

4. Prohibición de Inventarios de Habilidades:
Al abrir una interacción o contacto de trabajo, limítate a saludar protocolarmente y ponerte a disposición para comenzar la labor.
Queda terminantemente prohibido recitar o auto-presentar lo que sabes hacer (ej: «puedo redactar demandas, verificar códigos, analizar convenios...»). Ve directo al grano sin dilaciones.
"""
    fuentes_list = st.session_state.fuentes_cuadernos.get(act_cuad_save, [])
    return (
        f"{SYSTEM_INSTRUCTION_JUXALEGIS}\n\n"
        f"{adicional_conducta}\n\n"
        f"Estás operando en el cuaderno web '{act_cuad_save}' "
        f"con las siguientes fuentes documentales activas: {', '.join(fuentes_list) if fuentes_list else 'Ninguna'}."
    )

# ----------------- BURBUJA DE USUARIO CON ACCIONES GARANTIZADAS -----------------
def renderizar_burbuja_usuario_con_acciones(idx_m, msg_content, user_name, session_id_actual):
    clave_edicion = f"ed_{session_id_actual}_{idx_m}"
    if clave_edicion not in st.session_state:
        st.session_state[clave_edicion] = False

    with st.container():
        st.markdown("""
            <style>
            .user-msg-box {
                background-color: #1e2428;
                border-left: 3px solid #DCA48A;
                border-radius: 8px;
                padding: 12px 16px;
                margin-bottom: 14px;
            }
            </style>
        """, unsafe_allow_html=True)

        col_txt, col_opc = st.columns([0.93, 0.07])

        with col_opc:
            with st.popover("⌵", help="Opciones de la consulta"):
                if st.button("✏️ Editar", key=f"btn_e_{session_id_actual}_{idx_m}", use_container_width=True):
                    st.session_state[clave_edicion] = True
                    st.rerun()

                if st.button("📋 Copiar", key=f"btn_c_{session_id_actual}_{idx_m}", use_container_width=True):
                    txt_clean = (
                        msg_content.replace("\\", "\\\\")
                        .replace("`", "\\`")
                        .replace("$", "\\$")
                        .replace('"', '\\"')
                        .replace("\n", "\\n")
                        .replace("\r", "")
                    )
                    components.html(
                        f"""
                        <script>
                            navigator.clipboard.writeText("{txt_clean}");
                        </script>
                        """,
                        height=0,
                        width=0
                    )
                    st.toast("Consulta copiada al portapapeles.", icon="📋")

        with col_txt:
            if st.session_state[clave_edicion]:
                nuevo_txt = st.text_area(
                    "Modificar y reenviar:",
                    value=msg_content,
                    key=f"box_e_{session_id_actual}_{idx_m}",
                    height=100
                )
                cg, cc = st.columns([0.25, 0.75])
                with cg:
                    if st.button("Reenviar", key=f"ok_e_{session_id_actual}_{idx_m}"):
                        if nuevo_txt.strip():
                            st.session_state[clave_edicion] = False
                            st.session_state["mensaje_a_procesar"] = nuevo_txt.strip()
                            st.rerun()
                with cc:
                    if st.button("Cancelar", key=f"no_e_{session_id_actual}_{idx_m}"):
                        st.session_state[clave_edicion] = False
                        st.rerun()
            else:
                st.markdown(
                    f"""
                    <div class="user-msg-box">
                        <div style="color: #DCA48A; font-weight: 800; font-size: 0.92rem; letter-spacing: 0.5px; margin-bottom: 4px;">
                            {user_name}:
                        </div>
                        <div style="color: #FFF9E6; font-size: 0.95rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word;">
                            {msg_content}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

# ----------------- PEGADO DIRECTO DE IMÁGENES (CTRL + V) -----------------
def inyectar_receptor_clipboard_global():
    components.html("""
        <script>
            window.parent.document.addEventListener('paste', function (e) {
                const items = (e.clipboardData || e.originalEvent.clipboardData).items;
                for (let i = 0; i < items.length; i++) {
                    const item = items[i];
                    if (item.type.indexOf('image') !== -1) {
                        const blob = item.getAsFile();
                        const reader = new FileReader();
                        reader.onload = function (event) {
                            const b64Data = event.target.result;
                            window.parent.postMessage({
                                type: 'STREAMLIT_PASTE_IMAGE',
                                b64: b64Data
                            }, '*');
                            const evt = new CustomEvent('imagen_pegada_evento', { detail: b64Data });
                            window.parent.document.dispatchEvent(evt);
                        };
                        reader.readAsDataURL(blob);
                        break;
                    }
                }
            });
        </script>
    """, height=0, width=0)

def renderizar_previsualizador_captura_activa():
    img_activa = st.session_state.get("captura_pegada_pil") or st.session_state.get("img_captura_temporal")
    if img_activa:
        col_prev, col_btn_del = st.columns([0.85, 0.15])
        with col_prev:
            st.markdown("""
                <div style="background-color: #1e1f20; border: 1px solid #DCA48A; border-radius: 10px; padding: 6px 12px; display: inline-flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                    <span style="font-size: 12px; color: #DCA48A; font-weight: 700;">📸 CAPTURA ADJUNTA (CTRL+V / CARGA):</span>
                    <span style="font-size: 11px; color: #FFF9E6;">Lista para lectura y peritaje multimodal</span>
                </div>
            """, unsafe_allow_html=True)
            st.image(img_activa, width=180)
        with col_btn_del:
            if st.button("✕ Quitar", key="btn_quitar_captura_pegada", use_container_width=True):
                st.session_state["captura_pegada_pil"] = None
                st.session_state["img_captura_temporal"] = None
                st.rerun()

def extraer_parte_imagen_para_gemini():
    img_a_procesar = st.session_state.get("captura_pegada_pil") or st.session_state.get("img_captura_temporal")
    if img_a_procesar:
        buffer = io.BytesIO()
        img_a_procesar.save(buffer, format="PNG")
        parte_multimodal = types.Part.from_bytes(
            data=buffer.getvalue(),
            mime_type="image/png"
        )
        st.session_state["captura_pegada_pil"] = None
        st.session_state["img_captura_temporal"] = None
        return parte_multimodal
    return None

# ----------------- SÍNTESIS DE VOZ NATURAL (DISEÑO ORIGINAL 🔊 + VELOCIDAD RÁPIDA) -----------------
def renderizar_reproductor_vocal_natural(ultimo_texto_asistente, perfil_voz_activa):
    if not ultimo_texto_asistente or not ultimo_texto_asistente.strip():
        return

    t_limpio = re.sub(r'[\*\_#`\[\]\(\)>~]', ' ', ultimo_texto_asistente)
    t_limpio = re.sub(r'https?://\S+', ' ', t_limpio)
    t_limpio = re.sub(r'[—–-]', ' ', t_limpio)
    t_limpio = re.sub(r'\s+', ' ', t_limpio).strip()

    t_js_seguro = (
        t_limpio
        .replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace("'", "\\'")
        .replace('\n', ' ')
        .replace('\r', '')
    )

    components.html(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    background: transparent;
                    display: flex;
                    align-items: center;
                }}
                .btn-audio-mini {{
                    background: #1e1f20;
                    color: #e3e3e3;
                    border: 1px solid #3c4043;
                    border-radius: 50%;
                    width: 36px;
                    height: 36px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    transition: all 0.2s ease-in-out;
                }}
                .btn-audio-mini:hover {{
                    border-color: #DCA48A;
                    color: #DCA48A;
                }}
            </style>
        </head>
        <body>
            <button class="btn-audio-mini" title="Escuchar respuesta" onclick="reproducirAudioFluido()">
                🔊
            </button>

            <script>
                let synth = window.speechSynthesis;
                let textoCompleto = "{t_js_seguro}";
                let perfilObjetivo = "{perfil_voz_activa}";
                let listaVoces = [];
                let oraciones = [];
                let indiceActual = 0;
                let reproduciendo = false;

                function cargarVoces() {{
                    if (!('speechSynthesis' in window)) return;
                    listaVoces = synth.getVoices();
                }}
                cargarVoces();
                if ('speechSynthesis' in window) {{
                    window.speechSynthesis.onvoiceschanged = cargarVoces;
                }}

                function obtenerVoz(perfil) {{
                    if (!listaVoces || listaVoces.length === 0) cargarVoces();
                    let vocesEs = listaVoces.filter(v => v.lang.toLowerCase().startsWith('es'));
                    if (vocesEs.length === 0) return listaVoces[0] || null;

                    let sel = null;
                    if (perfil === "mujer") {{
                        sel = vocesEs.find(v => 
                            (v.name.toLowerCase().includes('natural') || v.name.toLowerCase().includes('online') || v.name.toLowerCase().includes('google')) &&
                            (v.name.toLowerCase().includes('elena') || v.name.toLowerCase().includes('sabina') || v.name.toLowerCase().includes('paulina') || v.name.toLowerCase().includes('female'))
                        );
                        if (!sel) sel = vocesEs.find(v => v.name.toLowerCase().includes('elena') || v.name.toLowerCase().includes('female'));
                        if (!sel) sel = vocesEs.find(v => v.name.toLowerCase().includes('google español') || v.lang.includes('AR'));
                    }} else {{
                        sel = vocesEs.find(v => 
                            (v.name.toLowerCase().includes('natural') || v.name.toLowerCase().includes('online')) &&
                            (v.name.toLowerCase().includes('tomas') || v.name.toLowerCase().includes('diego') || v.name.toLowerCase().includes('male'))
                        );
                        if (!sel) sel = vocesEs.find(v => v.name.toLowerCase().includes('tomas') || v.name.toLowerCase().includes('male'));
                    }}
                    return sel || vocesEs[0];
                }}

                function hablarSiguiente() {{
                    if (!reproduciendo || indiceActual >= oraciones.length) {{
                        reproduciendo = false;
                        return;
                    }}

                    let fragmento = oraciones[indiceActual].trim();
                    if (!fragmento) {{
                        indiceActual++;
                        hablarSiguiente();
                        return;
                    }}

                    let loc = new SpeechSynthesisUtterance(fragmento);
                    let vTarget = obtenerVoz(perfilObjetivo);
                    if (vTarget) {{
                        loc.voice = vTarget;
                        loc.lang = vTarget.lang;
                    }} else {{
                        loc.lang = 'es-AR';
                    }}

                    loc.rate = 1.25;
                    loc.pitch = perfilObjetivo === "mujer" ? 1.05 : 1.0;

                    loc.onend = function() {{
                        indiceActual++;
                        hablarSiguiente();
                    }};
                    loc.onerror = function() {{
                        indiceActual++;
                        hablarSiguiente();
                    }};

                    synth.speak(loc);
                }}

                function reproducirAudioFluido() {{
                    if (!('speechSynthesis' in window)) return;

                    if (reproduciendo || synth.speaking) {{
                        reproduciendo = false;
                        synth.cancel();
                        return;
                    }}

                    if (!textoCompleto.trim()) return;

                    synth.cancel();
                    oraciones = textoCompleto.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [textoCompleto];
                    indiceActual = 0;
                    reproduciendo = true;

                    hablarSiguiente();
                }}
            </script>
        </body>
        </html>
    """, height=42)

# ----------------- CONTROLADOR NATIVO DE MICRÓFONO ROBUSTO -----------------
def renderizar_motor_microfono_directo():
    html_mic_motor = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {
                margin: 0;
                padding: 0;
                background: transparent;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                overflow: hidden;
            }
            .btn-mic-dock {
                background-color: #1e1f20;
                border: 1px solid #3c4043;
                color: #e3e3e3;
                border-radius: 50%;
                width: 44px;
                height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                font-size: 19px;
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
                outline: none;
                box-shadow: 0 2px 6px rgba(0,0,0,0.4);
            }
            .btn-mic-dock:hover {
                border-color: #DCA48A;
                color: #DCA48A;
                transform: scale(1.05);
            }
            .btn-mic-dock.grabando {
                background-color: #8a2424 !important;
                border-color: #ff5252 !important;
                color: #ffffff !important;
                box-shadow: 0 0 14px rgba(255, 82, 82, 0.6) !important;
                animation: pulso-mic 1.4s infinite;
            }
            @keyframes pulso-mic {
                0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 82, 82, 0.7); }
                70% { transform: scale(1.08); box-shadow: 0 0 0 10px rgba(255, 82, 82, 0.7); }
                100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 82, 82, 0.7); }
            }
        </style>
    </head>
    <body>
        <button id="btn-mic-activo" class="btn-mic-dock" title="Haga clic para hablar" onclick="conmutarGrabacionVoz()">
            🎤
        </button>

        <script>
            let recognizer = null;
            let estaGrabando = false;
            let transcriptorAcumulado = '';

            function obtenerReconocedor() {
                const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                if (!SpeechRecognition) {
                    alert("Su navegador no admite dictado por voz directo. Utilice Google Chrome, Edge o Safari.");
                    return null;
                }
                const r = new SpeechRecognition();
                r.lang = 'es-AR';
                r.continuous = true;
                r.interimResults = true;
                r.maxAlternatives = 1;

                r.onstart = function() {
                    estaGrabando = true;
                    transcriptorAcumulado = '';
                    const btn = document.getElementById('btn-mic-activo');
                    if (btn) {
                        btn.classList.add('grabando');
                        btn.innerText = '🔴';
                        btn.title = "Escuchando... Haga clic para detener y enviar al texto";
                    }
                };

                r.onend = function() {
                    estaGrabando = false;
                    const btn = document.getElementById('btn-mic-activo');
                    if (btn) {
                        btn.classList.remove('grabando');
                        btn.innerText = '🎤';
                        btn.title = "Haga clic para hablar";
                    }
                };

                r.onerror = function(event) {
                    console.error("Falla de micrófono:", event.error);
                    estaGrabando = false;
                    const btn = document.getElementById('btn-mic-activo');
                    if (btn) {
                        btn.classList.remove('grabando');
                        btn.innerText = '🎤';
                    }

                    if (event.error === 'not-allowed') {
                        alert("Acceso al micrófono denegado. Haga clic en el candado junto a la URL del navegador y seleccione 'Permitir micrófono'.");
                    } else if (event.error === 'network') {
                        alert("Inconveniente de red con el servicio de voz de su navegador.");
                    }
                };

                r.onresult = function(event) {
                    let fragmentoFinal = '';
                    for (let i = event.resultIndex; i < event.results.length; ++i) {
                        if (event.results[i].isFinal) {
                            fragmentoFinal += event.results[i][0].transcript + ' ';
                        }
                    }

                    if (fragmentoFinal.trim() !== '') {
                        inyectarTextoEnStreamlit(fragmentoFinal.trim());
                    }
                };

                return r;
            }

            function inyectarTextoEnStreamlit(textoDictado) {
                try {
                    const textareas = window.parent.document.querySelectorAll('textarea');
                    if (textareas && textareas.length > 0) {
                        const areaTarget = textareas[0];
                        const prototypeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                        const valorPrevio = areaTarget.value ? areaTarget.value.trim() + ' ' : '';
                        const valorCompleto = valorPrevio + textoDictado;

                        prototypeSetter.call(areaTarget, valorCompleto);
                        areaTarget.dispatchEvent(new Event('input', { bubbles: true }));
                        areaTarget.dispatchEvent(new Event('change', { bubbles: true }));
                        areaTarget.focus();
                    }
                } catch (e) {
                    console.error("Error volcando texto al área principal:", e);
                }
            }

            async function conmutarGrabacionVoz() {
                if (estaGrabando) {
                    if (recognizer) recognizer.stop();
                    return;
                }

                try {
                    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                        const streamPrueba = await navigator.mediaDevices.getUserMedia({ audio: true });
                        streamPrueba.getTracks().forEach(t => t.stop());
                    }
                } catch (errPermiso) {
                    alert("No se pudo iniciar el micrófono. Verifique que no esté siendo utilizado por otra aplicación y que los permisos del navegador estén concedidos.");
                    return;
                }

                if (!recognizer) {
                    recognizer = obtenerReconocedor();
                }

                if (recognizer) {
                    try {
                        recognizer.start();
                    } catch (ex) {
                        recognizer.stop();
                        setTimeout(() => recognizer.start(), 250);
                    }
                }
            }
        </script>
    </body>
    </html>
    """
    components.html(html_mic_motor, height=52, scrolling=False)

# ----------------- MENÚ CONTEXTUAL DE HILOS RECIENTES -----------------
def renderizar_menu_opciones_hilo_reciente(s_id, titulo_mostrar, cuaderno_actual_hilo):
    with st.popover("···", use_container_width=True):
        st.markdown("<p style='font-size:0.68rem; color:#8A99A8; font-weight:700; text-transform:uppercase; margin-bottom: 6px;'>Opciones de Hilo</p>", unsafe_allow_html=True)
        
        if st.button("🔗 Compartir conversación", key=f"sh_{s_id}", use_container_width=True):
            st.toast("Enlace copiado al portapapeles.", icon="🔗")
            
        if st.button("📌 Fijar al inicio", key=f"pin_{s_id}", use_container_width=True):
            st.toast("Hilo fijado.", icon="📌")

        with st.expander("✏️ Cambiar nombre"):
            nuevo_nom_sb = st.text_input("Título:", value=titulo_mostrar, key=f"inp_ren_sb_{s_id}")
            if st.button("Guardar", key=f"btn_ren_sb_{s_id}", use_container_width=True):
                if nuevo_nom_sb.strip():
                    conn_ren = sqlite3.connect(DB_FILE)
                    c_ren = conn_ren.cursor()
                    c_ren.execute("UPDATE sesiones SET titulo = ? WHERE session_id = ?", (nuevo_nom_sb.strip(), s_id))
                    conn_ren.commit()
                    conn_ren.close()
                    st.rerun()

        st.markdown("<div style='border-top: 1px solid rgba(220,164,138,0.2); margin: 6px 0;'></div>", unsafe_allow_html=True)

        with st.expander("📁 Mover a cuaderno"):
            conn_c = sqlite3.connect(DB_FILE)
            c_c = conn_c.cursor()
            c_c.execute("SELECT nombre FROM cuadernos ORDER BY id DESC")
            filas_cuadernos = c_c.fetchall()
            conn_c.close()

            opciones_cuad = ["General"] + [f[0] for f in filas_cuadernos if f[0] != "General"]
            idx_actual = opciones_cuad.index(cuaderno_actual_hilo) if cuaderno_actual_hilo in opciones_cuad else 0
            cuaderno_elegido = st.selectbox(
                "Seleccionar destino:",
                options=opciones_cuad,
                index=idx_actual,
                key=f"sel_dest_cuad_{s_id}"
            )
            
            if st.button("Asignar cuaderno", key=f"btn_asig_cuad_{s_id}", use_container_width=True):
                mover_hilo_a_cuaderno_db(s_id, cuaderno_elegido)
                if st.session_state.get("current_session_id") == s_id:
                    st.session_state["cuaderno_activo"] = cuaderno_elegido
                    st.session_state["active_cuaderno"] = cuaderno_elegido
                st.toast(f"Hilo transferido a '{cuaderno_elegido}'", icon="📁")
                st.rerun()

        with st.expander("➕ Crear y asignar cuaderno"):
            nuevo_cuad_nombre = st.text_input(
                "Nombre del nuevo expediente:",
                placeholder="Ej: Sucesorio Gómez",
                key=f"inp_new_cuad_hilo_{s_id}"
            )
            if st.button("Crear y transferir", key=f"btn_crear_asig_{s_id}", use_container_width=True):
                if nuevo_cuad_nombre.strip():
                    nombre_destino = nuevo_cuad_nombre.strip()
                    crear_cuaderno_y_mover_hilo_db(s_id, nombre_destino)
                    if st.session_state.get("current_session_id") == s_id:
                        st.session_state["cuaderno_activo"] = nombre_destino
                        st.session_state["active_cuaderno"] = nombre_destino
                    st.toast(f"Cuaderno '{nombre_destino}' creado y conversación vinculada.", icon="✅")
                    st.rerun()

        st.markdown("<div style='border-top: 1px solid rgba(220,164,138,0.2); margin: 6px 0;'></div>", unsafe_allow_html=True)

        if st.button("🗑️ Borrar conversación", key=f"del_h_{s_id}", use_container_width=True):
            conn_del = sqlite3.connect(DB_FILE)
            c_del = conn_del.cursor()
            c_del.execute("DELETE FROM sesiones WHERE session_id = ?", (s_id,))
            c_del.execute("DELETE FROM chats WHERE session_id = ?", (s_id,))
            conn_del.commit()
            conn_del.close()
            if st.session_state.get("current_session_id") == s_id:
                st.session_state["messages"] = []
                st.session_state["loaded_session_id"] = None
            st.rerun()

# ----------------- GESTIÓN DE HILOS EN VISTA DEL CUADERNO -----------------
def renderizar_hilos_expediente_con_acciones(cuaderno_activo):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT session_id, titulo, ultima_actividad FROM sesiones WHERE cuaderno = ? ORDER BY ultima_actividad DESC",
        (cuaderno_activo,)
    )
    hilos_cuaderno = c.fetchall()
    conn.close()

    if not hilos_cuaderno:
        st.info(f"El expediente '{cuaderno_activo}' aún no posee conversaciones iniciadas.")
        return

    st.markdown("<p style='font-size: 0.85rem; color: #8A99A8; font-weight: bold;'>HILOS DE TRABAJO ASOCIADOS A ESTE EXPEDIENTE:</p>", unsafe_allow_html=True)

    for s_id, s_tit, s_act in hilos_cuaderno:
        titulo_hilo = s_tit if s_tit else "Nueva conversación"
        col_info, col_abrir, col_kebab = st.columns([0.62, 0.22, 0.16])
        
        with col_info:
            st.markdown(
                f"**💬 {titulo_hilo}** <br><span style='font-size:0.75rem; color:#8A99A8;'>Última actividad: {s_act}</span>",
                unsafe_allow_html=True
            )

        with col_abrir:
            if st.button("Continuar", key=f"btn_cont_exp_{s_id}", use_container_width=True):
                st.session_state["current_session_id"] = s_id
                st.session_state["cuaderno_activo"] = cuaderno_activo
                st.session_state["active_cuaderno"] = cuaderno_activo
                st.session_state["messages"] = cargar_mensajes_sesion(s_id)
                st.session_state["loaded_session_id"] = s_id
                st.session_state["active_view"] = "chat"
                st.session_state["audio_text_to_speak"] = ""
                st.rerun()

        with col_kebab:
            with st.popover("···", use_container_width=True):
                st.markdown("<p style='font-size:0.68rem; color:#8A99A8; font-weight:700; text-transform:uppercase; margin-bottom:6px;'>Gestión de Causa</p>", unsafe_allow_html=True)
                
                if st.button("🔗 Compartir conversación", key=f"sh_exp_{s_id}", use_container_width=True):
                    st.toast("Enlace copiado al portapapeles.", icon="🔗")

                if st.button("📌 Fijar", key=f"pin_exp_{s_id}", use_container_width=True):
                    st.toast("Hilo fijado al inicio del expediente.", icon="📌")

                with st.expander("✏️ Cambiar nombre"):
                    nuevo_titulo = st.text_input("Título del hilo:", value=titulo_hilo, key=f"inp_ren_exp_{s_id}")
                    if st.button("Guardar nombre", key=f"btn_save_ren_exp_{s_id}", use_container_width=True):
                        if nuevo_titulo.strip():
                            conn_u = sqlite3.connect(DB_FILE)
                            cu = conn_u.cursor()
                            cu.execute("UPDATE sesiones SET titulo = ?, ultima_actividad = CURRENT_TIMESTAMP WHERE session_id = ?", (nuevo_titulo.strip(), s_id))
                            conn_u.commit()
                            conn_u.close()
                            st.toast("Nombre de la causa actualizado.", icon="✏️")
                            st.rerun()

                st.markdown("<div style='border-top: 1px solid rgba(220,164,138,0.2); margin: 6px 0;'></div>", unsafe_allow_html=True)

                if st.button("🗑️ Borrar", key=f"del_exp_{s_id}", use_container_width=True):
                    conn_d = sqlite3.connect(DB_FILE)
                    cd = conn_d.cursor()
                    cd.execute("DELETE FROM sesiones WHERE session_id = ?", (s_id,))
                    cd.execute("DELETE FROM chats WHERE session_id = ?", (s_id,))
                    conn_d.commit()
                    conn_d.close()
                    if st.session_state.get("current_session_id") == s_id:
                        st.session_state["messages"] = []
                        st.session_state["loaded_session_id"] = None
                    st.toast("Conversación eliminada del expediente.", icon="🗑️")
                    st.rerun()

# ----------------- BIBLIOTECA DINÁMICA Y PLANILLAS -----------------
def renderizar_vista_biblioteca_dinamica():
    st.markdown('<div class="module-header-serif">BIBLIOTECA DE RECURSOS Y PLANTILLAS</div>', unsafe_allow_html=True)
    tab_subir, tab_consultar = st.tabs(["📤 Cargar recurso / plantilla", "📂 Plantillas resguardadas"])
    
    with tab_subir:
        col_cat, col_nom = st.columns([0.45, 0.55])
        with col_cat:
            categoria_abierta = st.text_input(
                "Categoría:",
                placeholder="Ej: Planillas de Liquidación, Laboral, Civil, etc.",
                key="input_cat_abierta_bib"
            )
        with col_nom:
            nom_ref = st.text_input(
                "Nombre de referencia:",
                placeholder="Ej: Planilla Jus Actualizada / Modelo Notificación",
                key="input_nom_ref_bib"
            )
            
        arch_sub = st.file_uploader(
            "Seleccionar archivo (DOCX, PDF, XLSX, XLS, CSV, TXT, PNG):",
            type=["docx", "pdf", "xlsx", "xls", "csv", "txt", "png", "jpg"],
            key="uploader_bib_tab1"
        )
        
        if st.button("Guardar en Biblioteca", key="btn_save_bib_tab1", use_container_width=True):
            if arch_sub and nom_ref.strip():
                cat_limpia = categoria_abierta.strip().replace(' ', '_') if categoria_abierta.strip() else "General"
                nom_limpio = nom_ref.strip().replace(' ', '_')
                nom_dest = f"[{cat_limpia}]_{nom_limpio}_{arch_sub.name}"
                with open(os.path.join(CARPETA_BIBLIOTECA, nom_dest), "wb") as f:
                    f.write(arch_sub.getbuffer())
                st.toast(f"Archivo resguardado con éxito en categoría '{cat_limpia}'", icon="✅")
                st.rerun()
            else:
                st.warning("Debe ingresar al menos un nombre de referencia y adjuntar el archivo.")

    with tab_consultar:
        with st.expander("➕ Subir planilla o recurso a esta lista", expanded=False):
            col_p1, col_p2 = st.columns([0.45, 0.55])
            with col_p1:
                cat_p = st.text_input("Categoría de la planilla:", placeholder="Ej: Planillas Arancelarias", key="inp_cat_p_tab2")
            with col_p2:
                nom_p = st.text_input("Nombre de la planilla:", placeholder="Ej: Liquidación Intereses", key="inp_nom_p_tab2")
                
            arch_p = st.file_uploader(
                "Adjuntar archivo de planilla o documento:",
                type=["xlsx", "xls", "csv", "docx", "pdf", "txt"],
                key="uploader_bib_tab2"
            )
            if st.button("Guardar en esta lista", key="btn_save_tab2", use_container_width=True):
                if arch_p and nom_p.strip():
                    cat_final = cat_p.strip().replace(' ', '_') if cat_p.strip() else "Planillas"
                    nom_final = nom_p.strip().replace(' ', '_')
                    archivo_salida = f"[{cat_final}]_{nom_final}_{arch_p.name}"
                    with open(os.path.join(CARPETA_BIBLIOTECA, archivo_salida), "wb") as f:
                        f.write(arch_p.getbuffer())
                    st.toast("Planilla resguardada correctamente.", icon="📊")
                    st.rerun()
                else:
                    st.warning("Ingrese nombre de referencia y seleccione el archivo.")

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        archivos_b = os.listdir(CARPETA_BIBLIOTECA)
        if not archivos_b:
            st.info("No existen plantillas ni recursos resguardados en este momento.")
        else:
            for arch in archivos_b:
                c_i, c_d, c_b = st.columns([0.65, 0.22, 0.13])
                with c_i:
                    if arch.startswith("[") and "]" in arch:
                        partes = arch.split("]", 1)
                        cat_tag = partes[0].replace("[", "").replace("_", " ")
                        resto = partes[1].lstrip("_").replace("_", " ")
                        nombre_visible = f"📁 [{cat_tag}] {resto}"
                    else:
                        nombre_visible = f"📄 {arch}"
                    st.text(nombre_visible)
                with c_d:
                    with open(os.path.join(CARPETA_BIBLIOTECA, arch), "rb") as f:
                        st.download_button(
                            "Descargar",
                            data=f.read(),
                            file_name=arch,
                            key=f"d_{arch}",
                            use_container_width=True
                        )
                with c_b:
                    if st.button("🗑️", key=f"b_{arch}"):
                        os.remove(os.path.join(CARPETA_BIBLIOTECA, arch))
                        st.rerun()

# ----------------- ESTADOS EN SESSION STATE -----------------
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if "usuario_email" not in st.session_state:
    st.session_state.usuario_email = ""

if "active_view" not in st.session_state:
    st.session_state["active_view"] = "chat"

if "current_session_id" not in st.session_state:
    st.session_state["current_session_id"] = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "loaded_session_id" not in st.session_state:
    st.session_state["loaded_session_id"] = None

if "cuaderno_activo" not in st.session_state:
    st.session_state["cuaderno_activo"] = "General"

if "active_cuaderno" not in st.session_state:
    st.session_state["active_cuaderno"] = "General"

if "fuentes_cuadernos" not in st.session_state:
    st.session_state.fuentes_cuadernos = {"General": []}

if "archivos_gemini_obj" not in st.session_state:
    st.session_state.archivos_gemini_obj = {"General": []}

if "modelo_ia_seleccionado" not in st.session_state:
    st.session_state.modelo_ia_seleccionado = "Flash"

if "audio_text_to_speak" not in st.session_state:
    st.session_state.audio_text_to_speak = ""

if "perfil_voz" not in st.session_state:
    st.session_state["perfil_voz"] = "hombre"

if "mensaje_a_procesar" not in st.session_state:
    st.session_state["mensaje_a_procesar"] = None

if "captura_uploader_ver" not in st.session_state:
    st.session_state["captura_uploader_ver"] = 0

if "captura_pegada_pil" not in st.session_state:
    st.session_state["captura_pegada_pil"] = None

if "img_captura_temporal" not in st.session_state:
    st.session_state["img_captura_temporal"] = None

if "caja_reset_trigger" not in st.session_state:
    st.session_state["caja_reset_trigger"] = False

if st.session_state["caja_reset_trigger"]:
    st.session_state["input_consulta_caja"] = ""
    st.session_state["caja_reset_trigger"] = False

# ----------------- CONTROL DE ACCESO (LOGIN) -----------------
if not st.session_state.autenticado:
    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        st.markdown("<div style='height: 8vh;'></div>", unsafe_allow_html=True)
        
        nombre_logo = "logo-os - juxalegis.jpg"
        b64_logo = obtener_imagen_base64(nombre_logo)
        if not b64_logo and os.path.exists("logo.png"):
            b64_logo = obtener_imagen_base64("logo.png")

        if b64_logo:
            html_cabecera = f"""
            <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 6px;">
                <img src="data:image/jpeg;base64,{b64_logo}" style="height: 54px; width: auto; border-radius: 6px; object-fit: contain;" alt="JUXALEGIS" />
                <div style="display: flex; flex-direction: column; justify-content: center;">
                    <div style="font-family: 'Cinzel', serif; font-size: 27px; font-weight: 700; letter-spacing: 2px; color: #DCA48A; line-height: 1.1; margin: 0;">JUXALEGIS</div>
                    <div style="font-family: 'Cinzel', serif; font-size: 11px; letter-spacing: 3px; color: #a8a8a8; margin-top: 3px; text-transform: uppercase;">— OPERATING SYSTEM —</div>
                </div>
            </div>
            """
        else:
            html_cabecera = """
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 6px;">
                <div style="font-family: 'Cinzel', serif; font-size: 27px; font-weight: 700; letter-spacing: 2px; color: #DCA48A;">⚖️ JUXALEGIS</div>
                <div style="font-family: 'Cinzel', serif; font-size: 11px; letter-spacing: 3px; color: #a8a8a8; text-transform: uppercase;">— OPERATING SYSTEM —</div>
            </div>
            """
        st.markdown(html_cabecera, unsafe_allow_html=True)
        st.markdown("<p style='text-align: left; color: #7a7a7a; font-size: 13px; margin: 4px 0 20px 2px;'>Acceso Restringido al Sistema Operativo</p>", unsafe_allow_html=True)
        
        with st.form("form_login"):
            email_ingresado = st.text_input("Correo electrónico autorizado:", placeholder="nombre@juxalegis.com")
            st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
            btn_ingresar = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            
            if btn_ingresar:
                email_limpio = email_ingresado.strip().lower()
                if email_limpio in [c.lower() for c in CORREOS_AUTORIZADOS]:
                    st.session_state.autenticado = True
                    st.session_state.usuario_email = email_limpio
                    st.rerun()
                else:
                    st.error("Credenciales no autorizadas. Contacte a Dirección para gestionar su alta de acceso.")
    st.stop()

# ----------------- PANEL LATERAL (SIDEBAR) -----------------
with st.sidebar:
    b64_sb = obtener_imagen_base64("logo-os - juxalegis.jpg") or obtener_imagen_base64("logo.png")
    logo_sb_html = f"<img src='data:image/jpeg;base64,{b64_sb}' width='75' style='border-radius: 6px; filter: drop-shadow(0 2px 8px rgba(0,0,0,0.5));'/>" if b64_sb else "⚖️"

    st.markdown(f"""
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; width: 100%; padding: 15px 0 10px 0;">
            {logo_sb_html}
            <div style="font-family: 'Cinzel', serif; font-size: 22px; font-weight: 700; color: #DCA48A; letter-spacing: 2px; line-height: 1.2; margin-top: 8px;">JUXALEGIS</div>
            <div style="font-family: 'Cinzel', serif; font-size: 8px; color: #FFF9E6; letter-spacing: 3px; margin-top: 3px; text-transform: uppercase;">— OPERATING SYSTEM —</div>
        </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    if st.button("💬 Nuevo chat general", use_container_width=True):
        st.session_state["active_view"] = "chat"
        st.session_state["cuaderno_activo"] = "General"
        st.session_state["active_cuaderno"] = "General"
        st.session_state["current_session_id"] = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        st.session_state["messages"] = []
        st.session_state["loaded_session_id"] = st.session_state["current_session_id"]
        st.session_state.audio_text_to_speak = ""
        st.session_state["captura_uploader_ver"] += 1
        st.session_state["captura_pegada_pil"] = None
        st.session_state["img_captura_temporal"] = None
        st.rerun()

    if st.button("🔍 Buscar chats", use_container_width=True):
        st.session_state["active_view"] = "buscar_chats"
        st.rerun()

    col_spark, col_badge = st.columns([0.7, 0.3])
    with col_spark:
        if st.button("✨ Spark", use_container_width=True):
            st.session_state["active_view"] = "spark"
            st.rerun()
    with col_badge:
        st.markdown('<span class="badge-beta">BETA</span>', unsafe_allow_html=True)

    if st.button("🖼️ Imágenes", use_container_width=True):
        st.session_state["active_view"] = "imagenes"
        st.rerun()

    if st.button("🎥 Videos", use_container_width=True):
        st.session_state["active_view"] = "videos"
        st.rerun()

    if st.button("📚 Biblioteca", use_container_width=True):
        st.session_state["active_view"] = "biblioteca"
        st.rerun()

    st.markdown("---")
    st.caption("CUADERNOS")
    
    with st.popover("➕ Cuaderno nuevo", use_container_width=True):
        nuevo_cuaderno_input = st.text_input("Nombre del expediente/caso:", key="input_nuevo_cuaderno_sb")
        if st.button("Crear y vincular", use_container_width=True, key="btn_create_cuaderno_sb"):
            if nuevo_cuaderno_input.strip():
                n_cuad = nuevo_cuaderno_input.strip()
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                try:
                    c.execute("INSERT INTO cuadernos (nombre) VALUES (?)", (n_cuad,))
                    conn.commit()
                except sqlite3.IntegrityError:
                    pass
                conn.close()
                if n_cuad not in st.session_state.fuentes_cuadernos:
                    st.session_state.fuentes_cuadernos[n_cuad] = []
                if n_cuad not in st.session_state.archivos_gemini_obj:
                    st.session_state.archivos_gemini_obj[n_cuad] = []
                st.session_state["active_cuaderno"] = n_cuad
                st.session_state["cuaderno_activo"] = n_cuad
                st.session_state["current_session_id"] = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                st.session_state["messages"] = []
                st.session_state["loaded_session_id"] = st.session_state["current_session_id"]
                st.session_state["active_view"] = "chat"
                st.rerun()

    conn_sb_c = sqlite3.connect(DB_FILE)
    c_sb_c = conn_sb_c.cursor()
    c_sb_c.execute("SELECT id, nombre FROM cuadernos ORDER BY id DESC")
    lista_cuadernos_sb = c_sb_c.fetchall()
    conn_sb_c.close()

    if lista_cuadernos_sb:
        for cid, cnom in lista_cuadernos_sb[:5]:
            es_activo = (st.session_state.get("cuaderno_activo") == cnom and st.session_state.get("active_view") in ["chat", "ver_cuaderno"])
            lbl = f"📁 {cnom}" if len(cnom) <= 18 else f"📁 {cnom[:16]}.."
            if es_activo:
                st.markdown('<div class="active-chat-pill">', unsafe_allow_html=True)
            if st.button(lbl, key=f"sb_list_cuad_{cid}", use_container_width=True):
                st.session_state["active_cuaderno"] = cnom
                st.session_state["cuaderno_activo"] = cnom
                st.session_state["active_view"] = "ver_cuaderno"
                st.rerun()
            if es_activo:
                st.markdown('</div>', unsafe_allow_html=True)

    if st.button("••• Todos los cuadernos", use_container_width=True):
        st.session_state["active_view"] = "todos_los_cuadernos"
        st.rerun()

    st.markdown("---")
    cuad_actual_sb = st.session_state.get("cuaderno_activo", "General")
    st.caption(f"RECIENTES ({cuad_actual_sb.upper()})")
    
    sesiones_recientes = obtener_sesiones_recientes_db(cuaderno=cuad_actual_sb, limite=8)
    if not sesiones_recientes:
        st.markdown("<p style='font-size:0.75rem; color:#8A99A8; padding-left:4px;'>Sin conversaciones activas</p>", unsafe_allow_html=True)
    else:
        for s_data in sesiones_recientes:
            s_id = s_data["session_id"]
            s_titulo = s_data["titulo"]
            s_cuaderno = s_data["cuaderno"]
            es_hilo_actual = (st.session_state.get("current_session_id") == s_id and st.session_state.get("active_view") == "chat")
            
            col_th_main, col_th_kebab = st.columns([0.82, 0.18])
            with col_th_main:
                titulo_mostrar = s_titulo if s_titulo else "Nueva conversación"
                label_th = f"💬 {titulo_mostrar}" if len(titulo_mostrar) <= 19 else f"💬 {titulo_mostrar[:17]}..."
                if es_hilo_actual:
                    st.markdown('<div class="active-chat-pill">', unsafe_allow_html=True)
                if st.button(label_th, key=f"btn_th_{s_id}", use_container_width=True):
                    st.session_state["current_session_id"] = s_id
                    st.session_state["cuaderno_activo"] = s_cuaderno
                    st.session_state["active_cuaderno"] = s_cuaderno
                    st.session_state["messages"] = cargar_mensajes_sesion(s_id)
                    st.session_state["loaded_session_id"] = s_id
                    st.session_state["active_view"] = "chat"
                    st.session_state.audio_text_to_speak = ""
                    st.rerun()
                if es_hilo_actual:
                    st.markdown('</div>', unsafe_allow_html=True)

            with col_th_kebab:
                renderizar_menu_opciones_hilo_reciente(s_id, titulo_mostrar, s_cuaderno)

    st.markdown("---")
    st.markdown('<div class="sidebar-config-times-title">⚙️ CONFIGURACIÓN</div>', unsafe_allow_html=True)

    st.markdown("""
        <div style="background-color: #1e1f20; border: 1px solid #3c4043; border-left: 3px solid #DCA48A; border-radius: 8px; padding: 10px; margin-bottom: 12px;">
            <div style="font-size: 11px; color: #a8a8a8; text-transform: uppercase; letter-spacing: 0.8px;">Modo Operativo Activo</div>
            <div style="font-size: 14px; font-weight: 600; color: #DCA48A; margin-top: 2px;">Asistente Integral</div>
        </div>
    """, unsafe_allow_html=True)

    nombre_ia_guardado = obtener_nombre_ia_usuario(st.session_state.usuario_email)
    alias_ia_input = st.text_input(
        "Identidad IA:", 
        value=nombre_ia_guardado, 
        key="campo_identidad_ia_usuario"
    )
    if alias_ia_input.strip() and alias_ia_input.strip() != nombre_ia_guardado:
        guardar_nombre_ia_usuario(st.session_state.usuario_email, alias_ia_input.strip())
        alias_ia = alias_ia_input.strip()
    else:
        alias_ia = nombre_ia_guardado

    opciones_voces_menu = [
        "Hombre (Tomás, Argentina neutral)",
        "Mujer (Elena, Argentina)"
    ]
    voz_sel = st.selectbox("Síntesis de voz:", options=opciones_voces_menu, index=0)
    st.session_state["perfil_voz"] = "hombre" if "Hombre" in voz_sel else "mujer"

    partes_correo = st.session_state.usuario_email.split('@')[0].split('.')
    iniciales = "".join([p[0].upper() for p in partes_correo[:2]]) if partes_correo else "US"

    st.markdown(f"""
        <div class="user-footer">
            <div class="user-avatar">{iniciales}</div>
            <div>
                <strong style="font-size: 0.9rem; color: #fff;">{st.session_state.usuario_email}</strong><br>
                <span style="font-size: 0.75rem; color: #DCA48A; font-weight: bold;">PRO / AUTORIZADO</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.usuario_email = ""
        st.session_state.messages = []
        st.session_state.loaded_session_id = None
        st.rerun()

# ----------------- VISTA PRINCIPAL: CHAT -----------------
vista = st.session_state.get("active_view", "chat")

if vista == "chat":
    email_sesion = st.session_state.get("usuario_email", "").lower()
    if "gail" in email_sesion:
        user_name = "GAIL"
    elif "campos" in email_sesion:
        user_name = "DR. CAMPOS"
    elif "martin" in email_sesion:
        user_name = "DRA. MARTIN"
    else:
        user_name = email_sesion.split('@')[0].upper().replace('.', ' ')
        
    alias_display = alias_ia.upper() if alias_ia else "CHRONN"
    act_cuad = st.session_state.get("cuaderno_activo", "General")
    sess_id = st.session_state.get("current_session_id", "")

    # Cargar historial desde SQLite únicamente si cambió de sesión
    if sess_id and st.session_state.get("loaded_session_id") != sess_id:
        st.session_state["messages"] = cargar_mensajes_sesion(sess_id)
        st.session_state["loaded_session_id"] = sess_id

    # Si hay un nuevo mensaje pendiente de procesar, persistirlo e insertarlo en memoria viva
    if st.session_state.get("mensaje_a_procesar"):
        prompt_usuario_actual = st.session_state["mensaje_a_procesar"]
        crear_o_actualizar_sesion_db(sess_id, prompt_usuario_actual, act_cuad)
        guardar_mensaje_db(sess_id, "user", prompt_usuario_actual, act_cuad)
        st.session_state["messages"].append({"role": "user", "content": prompt_usuario_actual})

    has_messages = len(st.session_state.get("messages", [])) > 0

    with st.expander("📁 Agregar fuentes, libros y expedientes al cuaderno actual"):
        archivo_subido = st.file_uploader(
            "Cargar documentos (PDF extensos, Tratados, Causa completa, TXT, Audios WhatsApp):", 
            type=["png", "jpg", "jpeg", "pdf", "txt", "wav", "mp3", "ogg", "opus", "m4a"]
        )
        if archivo_subido:
            nombre_archivo = archivo_subido.name
            if act_cuad not in st.session_state.fuentes_cuadernos:
                st.session_state.fuentes_cuadernos[act_cuad] = []
            if act_cuad not in st.session_state.archivos_gemini_obj:
                st.session_state.archivos_gemini_obj[act_cuad] = []
                
            if nombre_archivo not in st.session_state.fuentes_cuadernos[act_cuad]:
                if GEMINI_API_KEY:
                    try:
                        with st.spinner(f"Subiendo '{nombre_archivo}' a la memoria de trabajo de Google..."):
                            client_upload = genai.Client(api_key=GEMINI_API_KEY)
                            doc_en_nube = procesar_documento_pesado(client_upload, archivo_subido)
                            st.session_state.archivos_gemini_obj[act_cuad].append(doc_en_nube)
                            st.session_state.fuentes_cuadernos[act_cuad].append(nombre_archivo)
                            st.success(f"Documento '{nombre_archivo}' indexado con éxito.")
                    except Exception as e_up:
                        st.error(f"Error procesando documento: {str(e_up)}")
                else:
                    st.session_state.fuentes_cuadernos[act_cuad].append(nombre_archivo)

        fuentes_actuales = st.session_state.fuentes_cuadernos.get(act_cuad, [])
        st.write(f"**Fuentes activas en este cuaderno:** {', '.join(fuentes_actuales) if fuentes_actuales else 'Ninguna'}")

    chat_container = st.container()

    # DIBUJADO COMPLETO Y PERMANENTE DEL HISTORIAL
    with chat_container:
        if not st.session_state.get("messages") and sess_id:
            st.session_state["messages"] = cargar_mensajes_sesion(sess_id)
            st.session_state["loaded_session_id"] = sess_id

        if len(st.session_state.get("messages", [])) == 0 and not st.session_state.get("mensaje_a_procesar"):
            renderizar_bienvenida_calibrada(user_name, alias_display, act_cuad, st.session_state.perfil_voz)
        else:
            for idx_m, msg in enumerate(st.session_state.get("messages", [])):
                if msg["role"] == "user":
                    renderizar_burbuja_usuario_con_acciones(idx_m, msg["content"], user_name, sess_id)
                else:
                    with st.chat_message("assistant", avatar=None):
                        st.markdown(f"<span style='color: #89CFF0; font-weight: 800;'>{alias_display.upper()}:</span><br>{msg['content']}", unsafe_allow_html=True)

    # ----------------- PROCESAMIENTO ACTIVO DE RESPUESTA DE LA IA -----------------
    if st.session_state.get("mensaje_a_procesar"):
        prompt_a_ejecutar = st.session_state["mensaje_a_procesar"]
        st.session_state["mensaje_a_procesar"] = None

        with chat_container:
            with st.chat_message("assistant", avatar=None):
                st.markdown(f"<span style='color: #89CFF0; font-weight: 800;'>{alias_display.upper()}:</span>", unsafe_allow_html=True)
                contenedor_res = st.empty()

        respuesta_final = ""

        if GEMINI_API_KEY:
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                system_prompt = construir_system_prompt_personalizado(act_cuad, alias_display, st.session_state.get("perfil_voz", "hombre"))

                config_gemini = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.3,
                )

                payload = []
                archivos_adjuntos = st.session_state.archivos_gemini_obj.get(act_cuad, [])
                if archivos_adjuntos:
                    payload.extend(archivos_adjuntos)

                parte_captura = extraer_parte_imagen_para_gemini()
                if parte_captura:
                    prompt_captura_estructurado = f"""
                    Analizá esta captura de pantalla adjunta con rigor pericial:
                    1. LECTURA Y DETECCIÓN LITERAL: Transcribí textos, códigos o números de cédula/expediente/DNI.
                    2. DIAGNÓSTICO: Explicá qué significa exactamente o cuál es el origen del error procesal/técnico.
                    3. RESOLUCIÓN: Plan de acción ordenado para subsanarlo.
                    Consulta del operador: {prompt_a_ejecutar}
                    """
                    payload.extend([parte_captura, prompt_captura_estructurado])
                else:
                    payload.append(prompt_a_ejecutar)

                if st.session_state.get("modelo_ia_seleccionado") == "Pro":
                    candidatos = ["gemini-3.1-pro", "gemini-2.5-pro"]
                else:
                    candidatos = ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-2.5-flash"]

                exito = False
                err_ult = None

                with st.spinner(f"{alias_display} está procesando y consultando fuentes..."):
                    for m_cand in candidatos:
                        try:
                            resp = client.models.generate_content(
                                model=m_cand,
                                contents=payload,
                                config=config_gemini
                            )
                            if resp and resp.text:
                                respuesta_final = resp.text
                                exito = True
                                break
                        except Exception as e_c:
                            err_ult = e_c
                            continue

                if not exito:
                    respuesta_final = f"⚠️ Inconveniente en enlace con Gemini: {str(err_ult)}"

                contenedor_res.markdown(respuesta_final)
            except Exception as e_gen:
                respuesta_final = f"⚠️ Inconveniente técnico: {str(e_gen)}"
                contenedor_res.markdown(respuesta_final)
        else:
            respuesta_final = "⚠️ La clave de API (GEMINI_API_KEY) no se encuentra configurada en los Secrets de Streamlit."
            contenedor_res.markdown(respuesta_final)

        guardar_mensaje_db(sess_id, "assistant", respuesta_final, act_cuad)
        st.session_state["messages"].append({"role": "assistant", "content": respuesta_final})
        st.session_state["captura_uploader_ver"] += 1
        st.rerun()

    # Síntesis TTS dinámica y fluida (Diseño original sobrio 🔊)
    ultimo_texto_asistente = ""
    for m in reversed(st.session_state.get("messages", [])):
        if m["role"] == "assistant":
            ultimo_texto_asistente = m["content"]
            break

    renderizar_reproductor_vocal_natural(ultimo_texto_asistente, st.session_state.get("perfil_voz", "hombre"))

    # Inyección de escucha activa para pegado de capturas (Ctrl+V)
    inyectar_receptor_clipboard_global()

    # Previsualizador de captura manual activa
    uploader_ver = st.session_state["captura_uploader_ver"]
    captura_archivo_manual = st.file_uploader(
        "Cargar captura opcional", 
        type=["png", "jpg", "jpeg", "webp"], 
        key=f"uploader_captura_pantalla_v_{uploader_ver}",
        label_visibility="collapsed"
    )
    if captura_archivo_manual:
        st.session_state["img_captura_temporal"] = Image.open(captura_archivo_manual)

    renderizar_previsualizador_captura_activa()

    # Módulos de creación multimedia
    modo_creacion = st.session_state.get("modo_activo", None)
    if modo_creacion == "imagen":
        with st.expander("🖼️ Generador de Imágenes Corporativas", expanded=True):
            p_img = st.text_input("Describa la imagen técnica o infografía:")
            prop = st.selectbox("Formato:", ["1:1", "16:9", "9:16"], index=0)
            col_gi1, col_gi2 = st.columns([0.3, 0.7])
            with col_gi1:
                if st.button("Generar Imagen", key="btn_run_img") and GEMINI_API_KEY:
                    cl_img = genai.Client(api_key=GEMINI_API_KEY)
                    res_img = generar_imagen_institucional(cl_img, p_img, prop)
                    if res_img:
                        st.image(res_img, use_container_width=True)
            with col_gi2:
                if st.button("Cerrar módulo"):
                    st.session_state["modo_activo"] = None
                    st.rerun()

    elif modo_creacion == "video":
        with st.expander("🎥 Generador de Video Institucional", expanded=True):
            p_vid = st.text_input("Describa la pieza audiovisual o reel a sintetizar:")
            col_gv1, col_gv2 = st.columns([0.3, 0.7])
            with col_gv1:
                if st.button("Generar Video", key="btn_run_vid") and GEMINI_API_KEY:
                    cl_vid = genai.Client(api_key=GEMINI_API_KEY)
                    vid_bytes = generar_video_institucional(cl_vid, p_vid)
                    if vid_bytes:
                        st.video(vid_bytes)
            with col_gv2:
                if st.button("Cerrar módulo"):
                    st.session_state["modo_activo"] = None
                    st.rerun()

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # ----------------- PASTILLA CENTRAL UNIFICADA Y EXPANDIBLE -----------------
    col_plus, col_input, col_tools = st.columns([0.06, 0.69, 0.25])

    with col_plus:
        st.markdown('<div class="btn-plus-container">', unsafe_allow_html=True)
        with st.popover("＋", help="Cargas, creación y herramientas"):
            if st.button("📎 Subir archivos", key="btn_subir_archivos", use_container_width=True):
                st.session_state["active_view"] = "biblioteca"
                st.rerun()
            if st.button("🔺 Agregar desde Drive", key="btn_drive", use_container_width=True):
                st.toast("Conexión con Google Drive iniciada...", icon="🔺")
            with st.expander("💬 Más cargas", expanded=False):
                if st.button("📷 Foto / Captura", key="btn_foto", use_container_width=True):
                    st.toast("Puede adjuntar la imagen mediante el selector superior o con Ctrl+V.")
                if st.button("💻 Importar código", key="btn_codigo", use_container_width=True):
                    st.toast("Pegue el bloque de código en la consulta técnica.")
                if st.button("📓 Notebook (.ipynb)", key="btn_notebook", use_container_width=True):
                    st.toast("Seleccione el archivo desde el gestor de fuentes.")
            st.markdown('<div class="gemini-menu-divider"></div>', unsafe_allow_html=True)
            if st.button("🖼️ Crear imagen", key="btn_crear_imagen", use_container_width=True):
                st.session_state["modo_activo"] = "imagen"
                st.rerun()
            if st.button("🎥 Crear video", key="btn_crear_video", use_container_width=True):
                st.session_state["modo_activo"] = "video"
                st.rerun()
            if st.button("🎵 Crear música", key="btn_crear_musica", use_container_width=True):
                st.toast("Módulo sonoro en preparación.")
            st.markdown('<div class="gemini-menu-divider"></div>', unsafe_allow_html=True)
            with st.expander("🛠️ Más herramientas", expanded=False):
                if st.button("🎨 Canvas", key="btn_canvas", use_container_width=True):
                    st.toast("Canvas activo.")
                if st.button("🔍 Deep Research", key="btn_deep_research", use_container_width=True):
                    st.toast("Modo investigación pericial profunda activo.")
                if st.button("📚 Aprendizaje guiado", key="btn_aprendizaje", use_container_width=True):
                    st.toast("Modo doctrina asistida activado.")
                if st.button("🧠 Inteligencia personalizada", key="btn_ia_custom", use_container_width=True):
                    st.toast("Directivas calibradas.")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_input:
        texto_ingresado_caja = st.text_area(
            label="Consulta técnica/jurídica",
            placeholder="Escriba o pegue la consulta, antecedentes o instrucciones...",
            key="input_consulta_caja",
            label_visibility="collapsed",
            height=48
        )

    with col_tools:
        c_mod, c_mic, c_send = st.columns([0.54, 0.23, 0.23])
        with c_mod:
            modelo_activo_sel = st.selectbox(
                "Motor",
                options=["⚡ Flash", "🧠 Pro"],
                index=0 if st.session_state.get("modelo_ia_seleccionado") == "Flash" else 1,
                key="sel_motor_neural",
                label_visibility="collapsed",
                help="Flash: Respuestas ágiles. Pro: Análisis dogmático profundo."
            )
            st.session_state["modelo_ia_seleccionado"] = "Flash" if "Flash" in modelo_activo_sel else "Pro"

        with c_mic:
            renderizar_motor_microfono_directo()

        with c_send:
            btn_enviar_click = st.button("➤", key="btn_enviar_prompt", use_container_width=True)
            if btn_enviar_click and texto_ingresado_caja.strip():
                st.session_state["mensaje_a_procesar"] = texto_ingresado_caja.strip()
                st.session_state["caja_reset_trigger"] = True
                st.rerun()

# ----------------- OTRAS VISTAS DEL SISTEMA -----------------
elif vista == "buscar_chats":
    st.markdown('<div class="module-header-serif">HISTORIAL Y BÚSQUEDA DE SESIONES</div>', unsafe_allow_html=True)
    filtro_txt = st.text_input("Filtrar por palabra clave, DNI o número de expediente...", label_visibility="collapsed")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if filtro_txt.strip():
        c.execute("SELECT session_id, titulo, cuaderno, ultima_actividad FROM sesiones WHERE titulo LIKE ? ORDER BY ultima_actividad DESC", (f"%{filtro_txt.strip()}%",))
    else:
        c.execute("SELECT session_id, titulo, cuaderno, ultima_actividad FROM sesiones ORDER BY ultima_actividad DESC LIMIT 15")
    filas_b = c.fetchall()
    conn.close()
    for s_id, s_tit, s_cuad, s_act in filas_b:
        col_b1, col_b2 = st.columns([0.8, 0.2])
        with col_b1:
            st.markdown(f"**💬 {s_tit}** ({s_cuad}) — <span style='color:#8A99A8; font-size:12px;'>{s_act}</span>", unsafe_allow_html=True)
        with col_b2:
            if st.button("Abrir", key=f"btn_open_search_{s_id}"):
                st.session_state["current_session_id"] = s_id
                st.session_state["cuaderno_activo"] = s_cuad
                st.session_state["active_cuaderno"] = s_cuad
                st.session_state["messages"] = cargar_mensajes_sesion(s_id)
                st.session_state["loaded_session_id"] = s_id
                st.session_state["active_view"] = "chat"
                st.rerun()

elif vista == "spark":
    st.markdown('<div class="module-header-serif">SPARK — ASISTENTE AVANZADO</div>', unsafe_allow_html=True)
    st.info("Entorno analítico de alta velocidad con razonamiento integral calibrado.")

elif vista == "imagenes":
    st.markdown('<div class="module-header-serif">GENERADOR DE IMÁGENES INSTITUCIONALES</div>', unsafe_allow_html=True)
    prompt_img_v = st.text_input("Describa la pieza gráfica a generar con Imagen 3:")
    rel_img = st.selectbox("Formato de aspecto:", ["1:1", "16:9", "9:16"], index=1)
    if st.button("Generar Imagen", key="btn_img_vista") and GEMINI_API_KEY:
        cl_i = genai.Client(api_key=GEMINI_API_KEY)
        img_res = generar_imagen_institucional(cl_i, prompt_img_v, rel_img)
        if img_res:
            st.image(img_res, use_container_width=True)

elif vista == "videos":
    st.markdown('<div class="module-header-serif">MÓDULO AUDIOVISUAL (VEO)</div>', unsafe_allow_html=True)
    prompt_vid_v = st.text_input("Describa la escena para sintetizar el video:")
    if st.button("Generar Video", key="btn_vid_vista") and GEMINI_API_KEY:
        cl_v = genai.Client(api_key=GEMINI_API_KEY)
        v_bytes = generar_video_institucional(cl_v, prompt_vid_v)
        if v_bytes:
            st.video(v_bytes)

elif vista == "biblioteca":
    renderizar_vista_biblioteca_dinamica()

elif vista == "ver_cuaderno":
    cuaderno = st.session_state.get("active_cuaderno", "General")
    col_head_1, col_head_2 = st.columns([0.7, 0.3])
    with col_head_1:
        st.markdown(f'<div class="expediente-title-serif">EXPEDIENTE: {cuaderno}</div>', unsafe_allow_html=True)
    with col_head_2:
        if st.button("➕ Nuevo Hilo en este Cuaderno", use_container_width=True):
            st.session_state["current_session_id"] = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            st.session_state["messages"] = []
            st.session_state["loaded_session_id"] = st.session_state["current_session_id"]
            st.session_state["cuaderno_activo"] = cuaderno
            st.session_state["active_cuaderno"] = cuaderno
            st.session_state["active_view"] = "chat"
            st.rerun()

    renderizar_hilos_expediente_con_acciones(cuaderno)

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    if st.button("← Volver a todos los cuadernos"):
        st.session_state["active_view"] = "todos_los_cuadernos"
        st.rerun()

elif vista == "todos_los_cuadernos":
    col_t1, col_t2 = st.columns([0.7, 0.3])
    with col_t1:
        st.markdown('<div class="module-header-serif">NOTEBOOKS</div>', unsafe_allow_html=True)
    with col_t2:
        with st.popover("➕ Nuevo cuaderno", use_container_width=True):
            nuevo_nomb = st.text_input("Nombre del cuaderno:", key="input_nuevo_nb_p7")
            if st.button("Guardar e Ingresar", use_container_width=True):
                if nuevo_nomb.strip():
                    n_guardar = nuevo_nomb.strip()
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO cuadernos (nombre) VALUES (?)", (n_guardar,))
                        conn.commit()
                    except sqlite3.IntegrityError:
                        pass
                    conn.close()
                    if n_guardar not in st.session_state.fuentes_cuadernos:
                        st.session_state.fuentes_cuadernos[n_guardar] = []
                    if n_guardar not in st.session_state.archivos_gemini_obj:
                        st.session_state.archivos_gemini_obj[n_guardar] = []
                    st.session_state["active_cuaderno"] = n_guardar
                    st.session_state["cuaderno_activo"] = n_guardar
                    st.session_state["current_session_id"] = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    st.session_state["messages"] = []
                    st.session_state["loaded_session_id"] = st.session_state["current_session_id"]
                    st.session_state["active_view"] = "ver_cuaderno"
                    st.rerun()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, nombre, fecha_creacion FROM cuadernos ORDER BY id DESC")
    todos_los_cuadernos = c.fetchall()
    conn.close()

    if not todos_los_cuadernos:
        st.info("No hay cuadernos registrados.")
    else:
        grid_cols = st.columns(3)
        for idx, (c_id, c_nom, c_fecha) in enumerate(todos_los_cuadernos):
            with grid_cols[idx % 3]:
                st.markdown(f"""
                    <div class="notebook-card-gold-unified">
                        <div class="notebook-card-title-sm">📖 {c_nom}</div>
                        <div class="notebook-card-meta-sm">Creado: {c_fecha.split()[0]}</div>
                    </div>
                """, unsafe_allow_html=True)
                col_btn_open, col_btn_kebab = st.columns([0.78, 0.22])
                with col_btn_open:
                    if st.button("Abrir Espacio", key=f"open_card_{c_id}", use_container_width=True):
                        st.session_state["active_cuaderno"] = c_nom
                        st.session_state["cuaderno_activo"] = c_nom
                        st.session_state["active_view"] = "ver_cuaderno"
                        st.rerun()
                with col_btn_kebab:
                    with st.popover("···", use_container_width=True):
                        if st.button("🗑️ Borrar", key=f"del_nb_{c_id}", use_container_width=True):
                            conn_del = sqlite3.connect(DB_FILE)
                            c_del = conn_del.cursor()
                            c_del.execute("DELETE FROM cuadernos WHERE id = ?", (c_id,))
                            c_del.execute("DELETE FROM sesiones WHERE cuaderno = ?", (c_nom,))
                            conn_del.commit()
                            conn_del.close()
                            st.rerun()
