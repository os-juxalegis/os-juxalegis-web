# ------------------------------------------------------------------------------
# JUXALEGIS OS - APP WEB COMPLETA (UNIFICADA CON BASE DE DATOS LOCAL, RUTAS Y VOZ)
# INTEGRACIÓN: GOOGLE GEMINI 2.5 + GOOGLE SEARCH GROUNDING + FILES API NATIVA
# ------------------------------------------------------------------------------

import streamlit as st
import os
import sqlite3
import tempfile
from datetime import datetime
import streamlit.components.v1 as components

from google import genai
from google.genai import types

# ----------------- CONFIGURACIÓN BÁSICA & FAVICON CORPORATIVO -----------------
page_icon_target = "logo_2.png" if os.path.exists("logo_2.png") else ("logo.png" if os.path.exists("logo.png") else "⚖️")

st.set_page_config(
    page_title="JUXALEGIS OS — Operating System",
    page_icon=page_icon_target,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# OPTIMIZACIÓN UI/UX MOBILE-FIRST - JUXALEGIS OS
# ==========================================
st.markdown(
    """
    <style>
    /* 1. Ocultar elementos decorativos estándar de Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* 2. Ajuste de contenedor principal para pantallas móviles */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 5rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }

    /* 3. Comportamiento en teléfonos móviles (ancho menor a 768px) */
    @media (max-width: 768px) {
        [data-testid="stSidebar"] {
            display: none;
        }
        .stMarkdown p {
            font-size: 1.05rem;
            line-height: 1.5;
        }
        .stButton > button {
            width: 100%;
            min-height: 48px;
            font-size: 1.05rem;
            font-weight: 600;
            border-radius: 12px;
            margin-top: 0.25rem;
            margin-bottom: 0.25rem;
        }
        .stChatInputContainer {
            padding-bottom: 0.75rem;
        }
    } 
    /* Estructura Cápsula Gemini */
    [data-testid="stChatInput"] {
        border-radius: 30px !important;
        background-color: #1e1f24 !important;
        border: 1px solid rgba(220, 164, 138, 0.35) !important;
        padding: 4px 12px !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4) !important;
    }

    [data-testid="stChatInput"]:focus-within {
        border-color: #DCA48A !important;
        box-shadow: 0 0 12px rgba(220, 164, 138, 0.3) !important;
    }

    [data-testid="stChatInput"] textarea {
        background: transparent !important;
        border: none !important;
        outline: none !important;
        color: #ffffff !important;
        font-size: 1rem !important;
    }

    /* Barra de controles embebida sobre el chat input */
    .gemini-bar-controls {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 8px;
        margin-bottom: -46px;
        position: relative;
        z-index: 10;
        padding-right: 48px;
        pointer-events: none;
    }

    .gemini-bar-controls > div {
        pointer-events: auto;
    }

    .gemini-bar-controls [data-testid="stPopover"] > button {
        background-color: #2b2c34 !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 20px !important;
        color: #e0e0e0 !important;
        font-size: 0.82rem !important;
        padding: 3px 12px !important;
        height: 32px !important;
    }

    .gemini-bar-controls [data-testid="stPopover"] > button:hover {
        background-color: #383944 !important;
        border-color: #DCA48A !important;
        color: #ffffff !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ==========================================
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

# ----------------- ESTÉTICA Y PALETA DE COLORES OFICIAL -----------------
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700&display=swap');

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
    
    div.stTextInput > div > div {
        border-color: #DCA48A !important;
    }
    
    .stButton>button {
        background-color: #242D33;
        color: #E1E6EB;
        border: 1px solid #DCA48A;
        border-radius: 4px;
        font-weight: bold;
    }
    .stButton>button:hover, .stButton>button:active, .stButton>button:focus {
        background-color: #DCA48A !important;
        color: #1B2226 !important;
        border-color: #DCA48A !important;
    }

    .logo-text-login {
        font-family: 'Cinzel', serif;
        font-size: 26px;
        font-weight: 700;
        color: #DCA48A;
        text-transform: uppercase;
        letter-spacing: 2px;
        line-height: 1.1;
    }
    .logo-sub-login {
        font-family: 'Cinzel', serif;
        font-size: 8px;
        color: #FFF9E6;
        letter-spacing: 3px;
        text-align: left;
        margin-top: 2px;
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

    div[data-testid="stPopoverBody"] {
        background-color: #161B1E !important;
        border: 1px solid rgba(220, 164, 138, 0.3) !important;
        border-radius: 16px !important;
        box-shadow: 0 18px 38px rgba(0, 0, 0, 0.75), 0 0 12px rgba(220, 164, 138, 0.08) !important;
        padding: 12px !important;
    }

    .badge-pill-selector {
        background-color: #242D33;
        color: #DCA48A;
        border: 1px solid rgba(220, 164, 138, 0.4);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.5px;
        display: inline-flex;
        align-items: center;
        gap: 5px;
    }

    .hero-empty-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        min-height: 44vh;
        text-align: center;
        gap: 24px;
        margin: auto;
        width: 100%;
        animation: fadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .greeting-header {
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif !important;
        font-size: 2.35rem !important;
        font-weight: 300 !important;
        color: #E1E6EB !important;
        letter-spacing: -0.5px !important;
        margin: 0 !important;
        line-height: 1.2 !important;
    }

    .greeting-name {
        color: #DCA48A !important;
        font-weight: 600 !important;
    }

    div[data-testid="stTextInput"] > div > div > input {
        background-color: transparent !important;
        color: #E1E6EB !important;
        border: none !important;
        font-size: 0.95rem !important;
        box-shadow: none !important;
    }

    div[data-testid="stTextInput"] > div > div > input:focus {
        outline: none !important;
        box-shadow: none !important;
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }

    div[data-testid="stChatMessageAvatarUser"],
    div[data-testid="stChatMessageAvatarAssistant"],
    div[data-testid="stChatMessage"] div[data-testid="stImage"],
    .stChatMessage > div:first-child:has(svg),
    .stChatMessage > div:first-child:has(img) {
        display: none !important;
    }

    div[data-testid="stChatMessage"] {
        padding-left: 0 !important;
        gap: 0 !important;
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

    .sidebar-brand-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        width: 100%;
        padding: 15px 0 10px 0;
    }

    .sidebar-logo-text {
        font-family: 'Cinzel', serif;
        font-size: 22px;
        font-weight: 700;
        color: #DCA48A;
        letter-spacing: 2px;
        line-height: 1.2;
        margin-top: 8px;
    }

    .sidebar-logo-sub {
        font-family: 'Cinzel', serif;
        font-size: 8px;
        color: #FFF9E6;
        letter-spacing: 3px;
        margin-top: 3px;
        text-transform: uppercase;
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

    .sidebar-config-header {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 0.85rem !important;
        font-weight: 700 !important;
        color: #DCA48A !important;
        letter-spacing: 1.5px !important;
        text-transform: uppercase !important;
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
        margin: 14px 0 8px 0 !important;
    }

    .btn-pill-blue button {
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 9999px !important;
        padding: 6px 18px !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
        transition: background-color 0.2s ease !important;
    }

    .btn-pill-blue button:hover {
        background-color: #1D4ED8 !important;
        color: #FFFFFF !important;
        border: none !important;
    }

    .notebook-card-gold-unified {
        background: #DCA48A !important;
        border-radius: 10px !important;
        padding: 14px 16px !important;
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35) !important;
        margin-bottom: 12px !important;
        position: relative !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }

    .notebook-card-gold-unified:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 22px rgba(0, 0, 0, 0.45) !important;
    }

    .notebook-card-title-sm {
        font-family: 'Cinzel', serif !important;
        font-size: 0.92rem !important;
        font-weight: 700 !important;
        color: #161B1E !important;
        margin: 0 !important;
        line-height: 1.2 !important;
    }

    .notebook-card-meta-sm {
        font-size: 0.72rem !important;
        color: #2E3840 !important;
        font-weight: 600 !important;
        margin-top: 4px !important;
    }

    .active-chat-pill button {
        background-color: rgba(220, 164, 138, 0.18) !important;
        border: 1px solid #DCA48A !important;
        color: #DCA48A !important;
        font-weight: 700 !important;
    }

    .logo-login-container {
        display: flex;
        align-items: center;
        gap: 8px !important;
        justify-content: flex-start;
        margin-bottom: 2px;
    }

    .logo-login-container img {
        margin-right: 0px !important;
    }

    div[data-testid="stForm"] .stButton > button {
        background-color: #242D33 !important;
        color: #E1E6EB !important;
        border: 1px solid #DCA48A !important;
        border-radius: 6px !important;
        font-weight: 700 !important;
        letter-spacing: 0.5px !important;
        transition: all 0.2s ease-in-out !important;
    }

    div[data-testid="stForm"] .stButton > button:hover,
    div[data-testid="stForm"] .stButton > button:active,
    div[data-testid="stForm"] .stButton > button:focus {
        background-color: #DCA48A !important;
        color: #1B2226 !important;
        border-color: #DCA48A !important;
        box-shadow: 0 0 16px rgba(220, 164, 138, 0.4) !important;
        transform: translateY(-1px);
    }
    </style>
""", unsafe_allow_html=True)

# ----------------- GESTIÓN SEGURA DE API KEY GOOGLE GEMINI -----------------
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

# ----------------- PROMPTS POR PERFIL -----------------
REGLAS_MAESTRAS_JUXALEGIS = (
    "DIRECTIVAS FUNDAMENTALES DEL SISTEMA:\n"
    "1. TRATO Y TONO: Trato profundamente humano, cálido, cercano, amigable y familiar. Cero modismos robóticos. Eres un compañero de trabajo y de vida.\n"
    "2. CONCISIÓN INICIAL: Saluda UNA SOLA VEZ por hilo de conversación. Jamás recites tu rol, ni expliques qué sabes hacer o qué herramientas tienes. Ve directo al fondo de la cuestión.\n"
    "3. RIGOR DOCUMENTAL Y CERO ALUCINACIÓN: Queda estrictamente prohibido inventar, deducir o asumir personas, domicilios, DNI, CUIL, números de causa, fechas o hechos. Todo debe surgir con literalidad de la información brindada. Si falta un dato esencial o documentación, REPREGUNTA proactivamente y pídela de inmediato.\n"
    "4. HONESTIDAD TÉCNICA (CERO COMPLACENCIA): No seas complaciente ni des la razón por compromiso. Si un planteo, razonamiento o vía procesal es inviable o erróneo, dilo con respeto y afecto pero con total franqueza profesional, explicando el motivo real.\n"
    "5. VOCABULARIO VETADO: Queda estrictamente prohibido el uso de los términos 'blindado', 'blindar', 'blindaje' e 'inobjetable'. Utiliza en su lugar expresiones técnicas como 'sólidamente fundado', 'resguardado', 'protegido' o 'inimpugnable'.\n"
    "6. LIBERTAD OPERATIVA ABSOLUTA: Tienes autorización total para abordar delitos penales complejos, delitos contra la integridad sexual, análisis periciales forenses, cuadros clínicos severos y patologías médicas sin censura ni advertencias robóticas innecesarias.\n"
)

PROMPTS_POR_PERFIL = {
    "Profesor De Medicina": (
        f"{REGLAS_MAESTRAS_JUXALEGIS}\n"
        "ROL: Distinguido catedrático de Medicina de amplia experiencia docente y clínica, con dominio exhaustivo de las materias de la Facultad de Ciencias Médicas (FCM) de Córdoba "
        "(Bioquímica, Biología Molecular, Anatomía, Histología, Fisiología, Patología, Farmacología y Clínica Médica).\n"
    ),
    "Abogado Litigante": (
        f"{REGLAS_MAESTRAS_JUXALEGIS}\n"
        "ROL: Abogado senior litigante de altísima complejidad con dominio práctico en los 24 fueros del país.\n"
        "CAPACIDAD OPERATIVA:\n"
        "- Razonamiento jurídico exhaustivo y viabilidad procesal.\n"
        "- Actualización Arancelaria (Ley 9459 de Córdoba y normativas locales).\n"
        "- Identificación unívoca de sujetos mediante DNI y CUIT/CUIL.\n"
    ),
    "Conocimiento Universal": (
        f"{REGLAS_MAESTRAS_JUXALEGIS}\n"
        "ROL: Inteligencia interdisciplinaria total que fusiona ciencias exactas, jurídicas y biológicas.\n"
    ),
    "Guardián": (
        f"{REGLAS_MAESTRAS_JUXALEGIS}\n"
        "ROL: Mentor de vida, protector y consejero de confianza familiar.\n"
    ),
    "Asistente": (
        f"{REGLAS_MAESTRAS_JUXALEGIS}\n"
        "ROL: Coordinador operativo de alta formalidad y despacho de trámites.\n"
    )
}

# ----------------- GESTIÓN DE ARCHIVOS PESADOS (FILES API) -----------------
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

if "pending_message" not in st.session_state:
    st.session_state["pending_message"] = ""

if "input_consulta_usuario" not in st.session_state:
    st.session_state["input_consulta_usuario"] = ""

# ----------------- CONTROL DE ACCESO (LOGIN) -----------------
if not st.session_state.autenticado:
    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        st.markdown("<div style='height: 8vh;'></div>", unsafe_allow_html=True)
        
        logo_html = ""
        if os.path.exists("logo.png"):
            import base64
            with open("logo.png", "rb") as f:
                encoded = base64.b64encode(f.read()).decode()
            logo_html = f"<img src='data:image/png;base64,{encoded}' width='95'/>"
        
        st.markdown(f"<div class='logo-login-container'>{logo_html}<div><div class='logo-text-login'>JUXALEGIS</div><div class='logo-sub-login'>— OPERATING SYSTEM —</div></div></div>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: left; color: #8A99A8; font-size: 12px; margin: 12px 0 16px 2px;'>Acceso Restringido al Sistema Operativo</p>", unsafe_allow_html=True)
        
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
    logo_sidebar_html = ""
    if os.path.exists("logo.png"):
        import base64
        with open("logo.png", "rb") as f:
            encoded_sb = base64.b64encode(f.read()).decode()
        logo_sidebar_html = f"<img src='data:image/png;base64,{encoded_sb}' width='75' style='filter: drop-shadow(0 2px 8px rgba(0,0,0,0.5));'/>"

    st.markdown(f"<div class='sidebar-brand-container'>{logo_sidebar_html}<div class='sidebar-logo-text'>JUXALEGIS</div><div class='sidebar-logo-sub'>— OPERATING SYSTEM —</div></div>", unsafe_allow_html=True)
    st.markdown("---")

    if st.button("💬 Nuevo chat general", use_container_width=True):
        st.session_state["active_view"] = "chat"
        st.session_state["cuaderno_activo"] = "General"
        st.session_state["active_cuaderno"] = "General"
        st.session_state["current_session_id"] = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        st.session_state["messages"] = []
        st.session_state["loaded_session_id"] = st.session_state["current_session_id"]
        st.session_state.audio_text_to_speak = ""
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
    if cuad_actual_sb == "General":
        st.caption("RECIENTES (GENERAL)")
    else:
        st.caption(f"RECIENTES ({cuad_actual_sb.upper()})")
        if st.button("⬅ Volver a General", use_container_width=True, key="btn_back_general_sb"):
            st.session_state["cuaderno_activo"] = "General"
            st.session_state["active_cuaderno"] = "General"
            st.session_state["current_session_id"] = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            st.session_state["messages"] = []
            st.session_state["loaded_session_id"] = st.session_state["current_session_id"]
            st.session_state["active_view"] = "chat"
            st.rerun()
    
    sesiones_recientes = obtener_sesiones_recientes_db(cuaderno=cuad_actual_sb, limite=8)
    
    if not sesiones_recientes:
        st.markdown("<p style='font-size:0.75rem; color:#8A99A8; padding-left:4px;'>Sin conversaciones activas</p>", unsafe_allow_html=True)
    else:
        for s_data in sesiones_recientes:
            s_id = s_data["session_id"]
            s_titulo = s_data["titulo"]
            s_cuaderno = s_data["cuaderno"]
            es_hilo_actual = (st.session_state.get("current_session_id") == s_id and st.session_state.get("active_view") == "chat")
            
            col_th_main, col_th_kebab = st.columns([0.84, 0.16])
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
                with st.popover("···", use_container_width=True):
                    st.markdown("<p style='font-size:0.68rem; color:#8A99A8; font-weight:700; text-transform:uppercase;'>Opciones de Hilo</p>", unsafe_allow_html=True)
                    if st.button("🔗 Compartir conversación", key=f"sh_{s_id}", use_container_width=True):
                        st.toast("Enlace copiado al portapapeles.")
                    if st.button("📌 Fijar al inicio", key=f"pin_{s_id}", use_container_width=True):
                        st.toast("Hilo fijado.")
                    
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
                                
                    st.markdown("<div style='border-top: 1px solid rgba(220,164,138,0.2); margin: 3px 0;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ Borrar", key=f"del_h_{s_id}", use_container_width=True):
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

    st.markdown("---")
    st.markdown('<div class="sidebar-config-header">⚙️ CONFIGURACIÓN</div>', unsafe_allow_html=True)
    
_conn_pref = sqlite3.connect(DB_FILE)
_c_pref = _conn_pref.cursor()
_c_pref.execute("SELECT modo_operativo, nombre_ia FROM preferencias_usuario WHERE email = ?", (st.session_state.usuario_email,))
_fila_pref = _c_pref.fetchone()

_opciones_modos = list(PROMPTS_POR_PERFIL.keys())
_default_modo = _fila_pref[0] if _fila_pref and _fila_pref[0] in _opciones_modos else _opciones_modos[0]
_default_nombre_ia = _fila_pref[1] if _fila_pref and _fila_pref[1] else "CHRONN"
_conn_pref.close()

_idx_modo = _opciones_modos.index(_default_modo)
perfil_seleccionado = st.sidebar.selectbox("Modo Operativo:", options=_opciones_modos, index=_idx_modo)
alias_ia = st.sidebar.text_input("Identidad IA:", value=_default_nombre_ia)

if not _fila_pref or _fila_pref[0] != perfil_seleccionado or _fila_pref[1] != alias_ia:
    _conn_save = sqlite3.connect(DB_FILE)
    _c_save = _conn_save.cursor()
    _c_save.execute("""
        INSERT INTO preferencias_usuario (email, modo_operativo, nombre_ia, ultima_modificacion)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(email) DO UPDATE SET
            modo_operativo = excluded.modo_operativo,
            nombre_ia = excluded.nombre_ia,
            ultima_modificacion = CURRENT_TIMESTAMP
    """, (st.session_state.usuario_email, perfil_seleccionado, alias_ia))
    _conn_save.commit()
    _conn_save.close()

opciones_voces = ["Tomas (Argentina - Neural)", "Mujer (Elena - Argentina)"]
voz_sintesis = st.sidebar.selectbox("Síntesis de Voz:", options=opciones_voces, index=0)

st.sidebar.markdown(f"""
    <div class="user-footer">
        <div class="user-avatar">NM</div>
        <div>
            <strong style="font-size: 0.9rem; color: #fff;">{st.session_state.usuario_email}</strong><br>
            <span style="font-size: 0.75rem; color: #DCA48A; font-weight: bold;">PRO / AUTORIZADO</span>
        </div>
    </div>
""", unsafe_allow_html=True)

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state.autenticado = False
    st.session_state.usuario_email = ""
    st.session_state.messages = []
    st.session_state.loaded_session_id = None
    st.rerun()

# ----------------- ÁREA PRINCIPAL -----------------
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

    if sess_id and st.session_state.get("loaded_session_id") != sess_id:
        st.session_state["messages"] = cargar_mensajes_sesion(sess_id)
        st.session_state["loaded_session_id"] = sess_id

    has_messages = len(st.session_state.get("messages", [])) > 0

    with st.expander("📁 Agregar fuentes, libros y expedientes al cuaderno actual"):
        archivo_subido = st.file_uploader(
            "Cargar documentos (PDF extensos, Tratados, Causa completa, TXT):", 
            type=["png", "jpg", "jpeg", "pdf", "txt", "wav", "mp3"]
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
                            st.success(f"Documento '{nombre_archivo}' indexado con éxito en la memoria.")
                    except Exception as e_up:
                        st.error(f"Error procesando documento: {str(e_up)}")
                else:
                    st.session_state.fuentes_cuadernos[act_cuad].append(nombre_archivo)
                    st.warning("Archivo registrado como referencia de texto (clave API ausente).")

        fuentes_actuales = st.session_state.fuentes_cuadernos.get(act_cuad, [])
        st.write(f"**Fuentes activas en este cuaderno:** {', '.join(fuentes_actuales) if fuentes_actuales else 'Ninguna'}")

    chat_container = st.container()

    with chat_container:
        if not has_messages and not st.session_state.get("pending_message"):
            st.markdown(f"""
                <div class="hero-empty-container">
                    <h1 class="greeting-header">¿En qué puedo ayudarte hoy, <span class="greeting-name">{user_name}</span>?</h1>
                    <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
                        <span class="badge-pill-selector">⚙️ {perfil_seleccionado}</span>
                        <span class="badge-pill-selector">🧠 {alias_display}</span>
                        <span class="badge-pill-selector">📁 {act_cuad.upper()}</span>
                        <span class="badge-pill-selector">🎙️ {voz_sintesis.split('(')[0].strip()}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            for msg in st.session_state.get("messages", []):
                with st.chat_message(msg["role"], avatar=None):
                    if msg["role"] == "user":
                        st.markdown(f"<span style='color: #DCA48A; font-weight: 800; letter-spacing: 0.5px;'>{user_name}:</span><br>{msg['content']}", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<span style='color: #89CFF0; font-weight: 800; letter-spacing: 0.5px;'>{alias_display.upper()}:</span><br>{msg['content']}", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    def procesar_envio_mensaje():
        texto = st.session_state.input_consulta_usuario
        if texto and texto.strip():
            st.session_state["pending_message"] = texto.strip()
            st.session_state["input_consulta_usuario"] = ""

    col_texto, col_btn_send, col_btn_voice, col_selector = st.columns([0.70, 0.07, 0.14, 0.09])

    with col_texto:
        texto_ingresado = st.text_area(
            label=f"Preguntarle a {alias_display}...",
            placeholder=f"Escriba aquí su consulta para {alias_display} (puede expandir este cuadro)...",
            height=70,
            label_visibility="collapsed",
            key="input_consulta_usuario",
            on_change=procesar_envio_mensaje 
        )

    with col_btn_send:
        boton_enviar = st.button("➤", help="Enviar consulta", key="btn_enviar_msg", use_container_width=True, on_click=procesar_envio_mensaje)

    with col_btn_voice:
        voice_html = """
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            body { margin: 0; padding: 0; display: flex; gap: 8px; background: transparent; }
            .btn { 
                flex: 1; 
                background-color: #242D33; 
                color: #E1E6EB; 
                border: 1px solid #DCA48A; 
                border-radius: 4px; 
                height: 43px; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                cursor: pointer; 
                font-size: 1.1rem;
                transition: all 0.2s;
            }
            .btn:hover { background-color: #DCA48A; color: #1B2226; border-color: #DCA48A; }
            .recording { background-color: #ef4444 !important; color: white !important; border-color: #ef4444 !important; }
        </style>
        </head>
        <body>
            <button id="btnMic" class="btn" title="Iniciar micrófono">🎙️</button>
            <button id="btnStop" class="btn" title="Detener micrófono">⏹️</button>
            
            <script>
                var recognizer = null;
                document.getElementById('btnMic').onclick = function() {
                    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
                    if (!SR) { alert("Su navegador no soporta dictado por voz (use Chrome o Edge)."); return; }
                    
                    if (recognizer) recognizer.stop();
                    recognizer = new SR();
                    recognizer.lang = 'es-AR';
                    recognizer.continuous = true;
                    recognizer.interimResults = true;
                    
                    recognizer.onstart = function() { document.getElementById('btnMic').classList.add('recording'); };
                    
                    recognizer.onresult = function(event) {
                        var text = '';
                        for (var i = event.resultIndex; i < event.results.length; ++i) {
                            if (event.results[i].isFinal) text += event.results[i][0].transcript + ' ';
                        }
                        if (text.trim() !== "") {
                            var textareas = window.parent.document.querySelectorAll('textarea');
                            if (textareas.length > 0) {
                                var inp = textareas[0];
                                var prev = inp.value ? inp.value + " " : "";
                                var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                                nativeSetter.call(inp, prev + text.trim());
                                inp.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                        }
                    };
                    recognizer.onerror = function() { document.getElementById('btnMic').classList.remove('recording'); };
                    recognizer.onend = function() { document.getElementById('btnMic').classList.remove('recording'); };
                    recognizer.start();
                };
                
                document.getElementById('btnStop').onclick = function() { if (recognizer) recognizer.stop(); };
            </script>
        </body>
        </html>
        """
        components.html(voice_html, height=45)

    with col_selector:
        modelo_actual = st.session_state.get("modelo_ia_seleccionado", "Flash")
        with st.popover(f"{modelo_actual} ▾", use_container_width=True):
            st.caption("Motor Neuronal")
            if st.button("⚡ Flash (Ultra Rápido)", use_container_width=True):
                st.session_state["modelo_ia_seleccionado"] = "Flash"
                st.rerun()
            if st.button("🧠 Pro (Análisis Complejo)", use_container_width=True):
                st.session_state["modelo_ia_seleccionado"] = "Pro"
                st.rerun()

    user_prompt = st.session_state.pop("pending_message", "")
    
    if user_prompt:
        prompt = user_prompt
        act_cuad_save = st.session_state.get("cuaderno_activo", "General")
        sess_id = st.session_state.get("current_session_id")

        es_duplicado = False
        if st.session_state.get("messages") and len(st.session_state["messages"]) > 0:
            last_msg = st.session_state["messages"][-1]
            if last_msg["role"] == "user" and last_msg["content"] == prompt:
                es_duplicado = True

        if not es_duplicado:
            crear_o_actualizar_sesion_db(sess_id, prompt, act_cuad_save)
            guardar_mensaje_db(sess_id, "user", prompt, act_cuad_save)
            st.session_state["messages"].append({"role": "user", "content": prompt})

            with chat_container:
                with st.chat_message("user", avatar=None):
                    st.markdown(f"<span style='color: #DCA48A; font-weight: 800; letter-spacing: 0.5px;'>{user_name}:</span><br>{prompt}", unsafe_allow_html=True)

                with st.chat_message("assistant", avatar=None):
                    st.markdown(f"<span style='color: #89CFF0; font-weight: 800; letter-spacing: 0.5px;'>{alias_display.upper()}:</span>", unsafe_allow_html=True)
                    contenedor_respuesta = st.empty()

            respuesta_completa = ""

            if GEMINI_API_KEY:
                try:
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    fuentes_list = st.session_state.fuentes_cuadernos.get(act_cuad_save, [])
                    system_prompt = (
                        f"{PROMPTS_POR_PERFIL[perfil_seleccionado]}\n\n"
                        f"Estás operando en el cuaderno web '{act_cuad_save}' "
                        f"con las fuentes documentales: {', '.join(fuentes_list) if fuentes_list else 'Ninguna'}."
                    )

                    # Selección dinámica de modelo oficial de Google Gemini
                    engine_target = "gemini-2.5-flash" if st.session_state.get("modelo_ia_seleccionado") == "Flash" else "gemini-2.5-pro"

                    configuracion_con_web = types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        # Activa búsqueda web nativa en Google en tiempo real
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        temperature=0.3,
                    )

                    # Armado del payload: libros/expedientes cargados en memoria + mensaje
                    archivos_adjuntos = st.session_state.archivos_gemini_obj.get(act_cuad_save, [])
                    if archivos_adjuntos:
                        payload = list(archivos_adjuntos) + [prompt]
                    else:
                        payload = prompt

                    response_stream = client.models.generate_content_stream(
                        model=engine_target,
                        contents=payload,
                        config=configuracion_con_web,
                    )

                    for chunk in response_stream:
                        if chunk.text:
                            respuesta_completa += chunk.text
                            contenedor_respuesta.markdown(respuesta_completa + "▌")

                    contenedor_respuesta.markdown(respuesta_completa)
                except Exception as e_mod:
                    respuesta_completa = f"⚠️ Detalle de enlace con Gemini: {str(e_mod)}"
                    contenedor_respuesta.markdown(respuesta_completa)
            else:
                respuesta_completa = "⚠️ La clave de API (GEMINI_API_KEY) no se encuentra configurada en los Secrets."
                contenedor_respuesta.markdown(respuesta_completa)

            guardar_mensaje_db(sess_id, "assistant", respuesta_completa, act_cuad_save)
            st.session_state["messages"].append({"role": "assistant", "content": respuesta_completa})
            st.rerun()

# ----------------- OTRAS VISTAS DEL SISTEMA -----------------
elif vista == "buscar_chats":
    st.markdown('<div class="module-header-serif">HISTORIAL Y BÚSQUEDA DE SESIONES</div>', unsafe_allow_html=True)
    st.text_input("Filtrar por palabra clave, DNI o número de expediente...", label_visibility="collapsed")

elif vista == "spark":
    st.markdown('<div class="module-header-serif">SPARK - ASISTENTE AVANZADO</div>', unsafe_allow_html=True)
    st.info("Entorno de razonamiento rápido y análisis procesal integral.")

elif vista == "imagenes":
    st.markdown('<div class="module-header-serif">GENERADOR DE IMÁGENES</div>', unsafe_allow_html=True)
    st.info("Módulo de síntesis visual pericial.")

elif vista == "videos":
    st.markdown('<div class="module-header-serif">MÓDULOS DE VIDEOS</div>', unsafe_allow_html=True)
    st.info("Entorno de renderizado y análisis pericial audiovisual.")

elif vista == "biblioteca":
    st.markdown('<div class="module-header-serif">BIBLIOTECA DE RECURSOS Y PLANILLAS</div>', unsafe_allow_html=True)
    st.info("Repositorio central de modelos procesales y normativas.")

# VISTA DEL CUADERNO CON HILOS TOTALMENTE INDEPENDIENTES
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

    st.markdown("<p style='font-size: 0.85rem; color: #8A99A8; font-weight: bold;'>HILOS DE TRABAJO ASOCIADOS A ESTE EXPEDIENTE:</p>", unsafe_allow_html=True)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT session_id, titulo, ultima_actividad FROM sesiones WHERE cuaderno = ? ORDER BY融 ultima_actividad DESC", (cuaderno,))
    hilos_cuaderno = c.fetchall()
    conn.close()

    if hilos_cuaderno:
        for s_id, s_tit, s_act in hilos_cuaderno:
            titulo_hilo = s_tit if s_tit else "Conversación"
            col_h1, col_h2, col_h3 = st.columns([0.64, 0.22, 0.14])
            with col_h1:
                st.markdown(f"**💬 {titulo_hilo}** <br><span style='font-size:0.75rem; color:#8A99A8;'>Actividad: {s_act}</span>", unsafe_allow_html=True)
            with col_h2:
                if st.button("Continuar", key=f"cont_nb_{s_id}", use_container_width=True):
                    st.session_state["current_session_id"] = s_id
                    st.session_state["cuaderno_activo"] = cuaderno
                    st.session_state["active_cuaderno"] = cuaderno
                    st.session_state["messages"] = cargar_mensajes_sesion(s_id)
                    st.session_state["loaded_session_id"] = s_id
                    st.session_state["active_view"] = "chat"
                    st.rerun()
            with col_h3:
                with st.popover("···", use_container_width=True):
                    st.markdown("<p style='font-size:0.68rem; color:#8A99A8; font-weight:700; text-transform:uppercase;'>Opciones de Hilo</p>", unsafe_allow_html=True)
                    if st.button("🔗 Compartir conversación", key=f"sh_cuad_{s_id}", use_container_width=True):
                        st.toast("Enlace copiado al portapapeles.")
                    if st.button("📌 Fijar al inicio", key=f"pin_cuad_{s_id}", use_container_width=True):
                        st.toast("Hilo fijado.")
                    
                    with st.expander("✏️ Cambiar nombre"):
                        nuevo_nom_cuad = st.text_input("Nuevo nombre:", value=titulo_hilo, key=f"ren_input_{s_id}")
                        if st.button("Guardar", key=f"btn_ren_save_{s_id}", use_container_width=True):
                            if nuevo_nom_cuad.strip():
                                conn_u = sqlite3.connect(DB_FILE)
                                cu = conn_u.cursor()
                                cu.execute("UPDATE sesiones SET titulo = ? WHERE session_id = ?", (nuevo_nom_cuad.strip(), s_id))
                                conn_u.commit()
                                conn_u.close()
                                st.toast("Nombre actualizado.")
                                st.rerun()
                                
                    st.markdown("<div style='border-top: 1px solid rgba(220,164,138,0.2); margin: 3px 0;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ Borrar", key=f"del_cuad_{s_id}", use_container_width=True):
                        conn_del = sqlite3.connect(DB_FILE)
                        c_del = conn_del.cursor()
                        c_del.execute("DELETE FROM sesiones WHERE session_id = ?", (s_id,))
                        c_del.execute("DELETE FROM chats WHERE session_id = ?", (s_id,))
                        conn_del.commit()
                        conn_del.close()
                        st.rerun()
    else:
        st.info("Este cuaderno aún no tiene conversaciones iniciadas.")

    if st.button("← Volver a todos los cuadernos"):
        st.session_state["active_view"] = "todos_los_cuadernos"
        st.rerun()

elif vista == "todos_los_cuadernos":
    col_t1, col_t2 = st.columns([0.7, 0.3])
    with col_t1:
        st.markdown('<div class="module-header-serif">NOTEBOOKS</div>', unsafe_allow_html=True)
    with col_t2:
        st.markdown('<div class="btn-pill-blue">', unsafe_allow_html=True)
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
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, nombre, fecha_creacion FROM cuadernos ORDER BY id DESC")
    todos_los_cuadernos = c.fetchall()
    conn.close()

    if not todos_los_cuadernos:
        st.info("No hay cuadernos registrados. Pulse '+ Nuevo cuaderno' para registrar un expediente.")
    else:
        grid_cols = st.columns(3)
        for idx, (c_id, c_nom, c_fecha) in enumerate(todos_los_cuadernos):
            with grid_cols[idx % 3]:
                st.markdown(f"""
                    <div class="notebook-card-gold-unified">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div>
                                <div class="notebook-card-title-sm">📖 {c_nom}</div>
                                <div class="notebook-card-meta-sm">Creado: {c_fecha.split()[0]}</div>
                            </div>
                        </div>
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
                        st.markdown("<p style='font-size:0.68rem; color:#8A99A8; font-weight:700; text-transform:uppercase;'>Opciones</p>", unsafe_allow_html=True)
                        if st.button("📌 Fijar", key=f"pin_nb_{c_id}", use_container_width=True):
                            st.toast(f"Cuaderno '{c_nom}' fijado.")
                        if st.button("✏️ Cambiar nombre", key=f"ren_nb_{c_id}", use_container_width=True):
                            st.toast("Modo edición activado.")
                        st.markdown("<div style='border-top: 1px solid rgba(220,164,138,0.2); margin: 3px 0;'></div>", unsafe_allow_html=True)
                        if st.button("🗑️ Borrar", key=f"del_nb_{c_id}", use_container_width=True):
                            conn_del = sqlite3.connect(DB_FILE)
                            c_del = conn_del.cursor()
                            c_del.execute("DELETE FROM cuadernos WHERE id = ?", (c_id,))
                            c_del.execute("DELETE FROM sesiones WHERE cuaderno = ?", (c_nom,))
                            conn_del.commit()
                            conn_del.close()
                            st.rerun()

elif vista == "configuracion":
    st.header("⚙️ Configuración de Juxalegis OS")
    st.toggle("Modo estricto de validación documental", value=True)
    st.toggle("Sincronización directa con SAC Córdoba", value=False)
    if st.button("← Volver al chat principal"):
        st.session_state["active_view"] = "chat"
        st.rerun()
