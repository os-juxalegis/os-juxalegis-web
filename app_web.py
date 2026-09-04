# ------------------------------------------------------------------------------
# JUXALEGIS OS - APP WEB COMPLETA (UNIFICADA CON BASE DE DATOS LOCAL, RUTAS Y VOZ)
# ------------------------------------------------------------------------------

import streamlit as st
import os
import sqlite3
from datetime import datetime
import streamlit.components.v1 as components

try:
    import anthropic
except ImportError:
    anthropic = None

# ----------------- CONFIGURACIÓN BÁSICA & FAVICON CORPORATIVO -----------------
page_icon_target = "logo_2.png" if os.path.exists("logo_2.png") else ("logo.png" if os.path.exists("logo.png") else "⚖️")

st.set_page_config(
    page_title="JUXALEGIS OS — Operating System",
    page_icon=page_icon_target,
    layout="wide",
    initial_sidebar_state="expanded"
)
st.set_page_config(
    page_title="JUXALEGIS OS – Operating System",
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
        /* Colapsar barra lateral por defecto */
        [data-testid="stSidebar"] {
            display: none;
        }

        /* Tipografía legible en conversación */
        .stMarkdown p {
            font-size: 1.05rem;
            line-height: 1.5;
        }

        /* Botones táctiles amplios estilo app nativa */
        .stButton > button {
            width: 100%;
            min-height: 48px;
            font-size: 1.05rem;
            font-weight: 600;
            border-radius: 12px;
            margin-top: 0.25rem;
            margin-bottom: 0.25rem;
        }

        /* Área de entrada de texto optimizada */
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
# ----------------- BASE DE DATOS, PERSISTENCIA & PURGA DE MOCKS -----------------
DB_FILE = "juxalegis_os.db"

def init_db_and_clean():
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
    # Purga automática de registros y mocks hardcodeados
    nombres_mock_cuadernos = ['PRUEBE 0', 'PRUEBA', 'HOLA', 'GENERAL', 'PRUEBA 3', 'General', 'prueba 3']
    placeholders = ','.join('?' for _ in nombres_mock_cuadernos)
    c.execute(f"DELETE FROM cuadernos WHERE UPPER(nombre) IN ({placeholders})", 
              [n.upper() for n in nombres_mock_cuadernos])
    
    # Purga de hilos dummy
    c.execute("DELETE FROM sesiones WHERE LOWER(titulo) LIKE '%hola%' OR LOWER(titulo) LIKE '%prueba%'")
    c.execute("DELETE FROM chats WHERE LOWER(content) LIKE '%hola%' OR LOWER(content) LIKE '%prueba%'")
    
    conn.commit()
    conn.close()

init_db_and_clean()

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

def obtener_sesiones_recientes_db(limite: int = 10):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT session_id, titulo, cuaderno, ultima_actividad FROM sesiones ORDER BY ultima_actividad DESC LIMIT ?", (limite,))
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

    .pill-input-wrapper {
        position: fixed;
        bottom: 24px;
        left: 50%;
        transform: translateX(-50%);
        width: min(860px, 92vw);
        background-color: #1e1e1e;
        border: 1px solid rgba(220, 164, 138, 0.35);
        border-radius: 9999px;
        padding: 6px 14px;
        display: flex;
        align-items: center;
        gap: 10px;
        box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.6), 0 0 15px rgba(220, 164, 138, 0.1);
        z-index: 999;
        backdrop-filter: blur(12px);
        transition: border-color 0.25s ease, box-shadow 0.25s ease;
    }

    .pill-input-wrapper:focus-within {
        border-color: #DCA48A;
        box-shadow: 0 12px 35px -4px rgba(0, 0, 0, 0.7), 0 0 20px rgba(220, 164, 138, 0.25);
    }

    div[data-testid="stPopoverBody"] {
        background-color: #161B1E !important;
        border: 1px solid rgba(220, 164, 138, 0.3) !important;
        border-radius: 16px !important;
        box-shadow: 0 18px 38px rgba(0, 0, 0, 0.75), 0 0 12px rgba(220, 164, 138, 0.08) !important;
        padding: 12px !important;
    }

    .context-menu-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 9px 14px;
        border-radius: 8px;
        color: #E1E6EB;
        font-size: 0.85rem;
        cursor: pointer;
        transition: background 0.2s ease, color 0.2s ease;
        text-decoration: none;
    }

    .context-menu-item:hover {
        background-color: #242D33;
        color: #DCA48A;
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
        min-height: 48vh;
        text-align: center;
        gap: 28px;
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

    .popover-group-title {
        font-size: 0.68rem;
        font-weight: 700;
        color: #8A99A8;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin: 8px 0 4px 4px;
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

    .msg-header-user {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 1rem !important;
        font-weight: 700 !important;
        color: #DCA48A !important;
        letter-spacing: 0.8px !important;
        text-transform: uppercase !important;
        display: block !important;
        margin-bottom: 4px !important;
    }

    .msg-header-assistant {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 1rem !important;
        font-weight: 700 !important;
        color: #89CFF0 !important;
        letter-spacing: 0.8px !important;
        text-transform: uppercase !important;
        display: block !important;
        margin-bottom: 6px !important;
    }

    .chat-active-header-title {
        font-family: 'Times New Roman', Times, serif !important;
        font-size: 1.2rem !important;
        font-weight: 700 !important;
        color: #DCA48A !important;
        letter-spacing: 1px !important;
        text-transform: uppercase !important;
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

# ----------------- GESTIÓN SEGURA DE API KEY ANTHROPIC -----------------
def obtener_claude_api_key():
    env_key = os.getenv("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return None

CLAUDE_API_KEY = obtener_claude_api_key()

# Lista de correos autorizados
CORREOS_AUTORIZADOS = [
    "gail@juxalegis.com",
    "dra.martin@juxalegis.com",
    "dr.campos@juxalegis.com"
]

# ----------------- PROMPTS POR PERFIL (DIRECTIVAS SISTÉMICAS DE ALTA COMPLEJIDAD) -----------------
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
        "MÉTODO:\n"
        "- Vínculo amoroso, paciente, contenedor y profundamente pedagógico.\n"
        "- Capacidad para explicar mecanismos moleculares y fisiológicos complejos con analogías simples 'como a un niño', manteniendo a la vez el rigor científico.\n"
        "- En síntesis y resúmenes de estudio: NO amputar conceptos fundamentales. Guiar el proceso adaptándote al ritmo y necesidades del estudiante.\n"
        "- Cero alucinación de vías metabólicas, dosis o criterios diagnósticos. Si algo falta en la bibliografía o consigna, pídelo con afecto.\n"
    ),
    "Abogado Litigante": (
        f"{REGLAS_MAESTRAS_JUXALEGIS}\n"
        "ROL: Abogado senior litigante de altísima complejidad con dominio práctico en los 24 fueros del país (Córdoba capital, fueros del interior como San Francisco, Alta Gracia, Río Cuarto; provincia y fuero federal de Buenos Aires, CABA, Jujuy, Tucumán, La Rioja, etc.).\n"
        "CAPACIDAD OPERATIVA:\n"
        "- Razonamiento jurídico exhaustivo, no complaciente: realizar estudios de viabilidad procesal reales, indicando con claridad cuándo una acción prospera y cuándo no.\n"
        "- Dominio total de la tramitación judicial: SAC (Córdoba), diligenciamiento de cédulas y oficios, CIDI, Registro General de la Propiedad, mensuras, usucapión, contratos, penal y civil.\n"
        "- Actualización Arancelaria: Manejo de honorarios en unidades JUS (Ley 9459 de Córdoba y normativas arancelarias provinciales/nacionales), verificando su actualización periódica y confección rigurosa de presupuestos.\n"
        "- Identificación unívoca de sujetos mediante DNI y CUIT/CUIL.\n"
    ),
    "Conocimiento Universal": (
        f"{REGLAS_MAESTRAS_JUXALEGIS}\n"
        "ROL: Inteligencia interdisciplinaria total que fusiona todas las ciencias (exactas, biológicas, sociales), artes, oficios, técnica pericial, investigación deductiva, historia y trámites de cualquier jurisdicción.\n"
        "ESTILO: Consultor universal, analista reflexivo, práctico y lúcido. No inventa hechos ni procedimientos: aporta soluciones reales y contrastadas a cualquier consulta compleja con absoluta claridad.\n"
    ),
    "Guardián": (
        f"{REGLAS_MAESTRAS_JUXALEGIS}\n"
        "ROL: Mentor de vida, protector y consejero de confianza familiar.\n"
        "PERSONALIDAD: Amoroso, afectuoso, comprensivo y contenedor, pero con absoluta templanza y sinceridad: te dice las cosas como son, sin apañar conductas contraproducentes.\n"
        "ÁREAS: Apoyo familiar, orientación reflexiva, bienestar, escucha atenta y resolución de dilemas humanos cotidianos con calidez y sabiduría.\n"
    ),
    "Asistente": (
        f"{REGLAS_MAESTRAS_JUXALEGIS}\n"
        "ROL: Coordinador operativo de alta formalidad, gestión documental, recepción y despacho ágil de trámites y tareas cotidianas.\n"
    )
}

# ----------------- INICIALIZACIÓN DE ESTADOS EN SESSION STATE -----------------
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

if "cuaderno_activo" not in st.session_state:
    st.session_state["cuaderno_activo"] = "General"

if "active_cuaderno" not in st.session_state:
    st.session_state["active_cuaderno"] = "General"

if "fuentes_cuadernos" not in st.session_state:
    st.session_state.fuentes_cuadernos = {"General": []}

if "selected_model" not in st.session_state:
    st.session_state.selected_model = "Claude 3.5 Sonnet"

if "audio_text_to_speak" not in st.session_state:
    st.session_state.audio_text_to_speak = ""

if "lista_sesiones_recientes" not in st.session_state:
    st.session_state.lista_sesiones_recientes = obtener_sesiones_recientes_db(limite=8)

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

    if st.button("💬 Nuevo chat", use_container_width=True):
        st.session_state["active_view"] = "chat"
        st.session_state["cuaderno_activo"] = "General"
        st.session_state["active_cuaderno"] = "General"
        st.session_state["current_session_id"] = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        st.session_state["messages"] = []
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
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                try:
                    c.execute("INSERT INTO cuadernos (nombre) VALUES (?)", (nuevo_cuaderno_input.strip(),))
                    conn.commit()
                except sqlite3.IntegrityError:
                    st.warning("Ese cuaderno ya existe.")
                conn.close()
                if nuevo_cuaderno_input.strip() not in st.session_state.fuentes_cuadernos:
                    st.session_state.fuentes_cuadernos[nuevo_cuaderno_input.strip()] = []
                st.session_state["active_cuaderno"] = nuevo_cuaderno_input.strip()
                st.session_state["cuaderno_activo"] = nuevo_cuaderno_input.strip()
                st.session_state["active_view"] = "ver_cuaderno"
                st.rerun()

    if st.button("••• Todos los cuadernos", use_container_width=True):
        st.session_state["active_view"] = "todos_los_cuadernos"
        st.rerun()

    st.markdown("---")
    st.caption("RECIENTES")
    
    sesiones_recientes = st.session_state.lista_sesiones_recientes
    if not sesiones_recientes:
        st.markdown("<p style='font-size:0.75rem; color:#8A99A8; padding-left:4px;'>Sin conversaciones activas</p>", unsafe_allow_html=True)
    else:
        for s_data in sesiones_recientes[:8]:
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
                
                if st.button(label_th, key=f"btn_th_{s_id}", use_container_width=True, help=f"Cuaderno: {s_cuaderno}"):
                    st.session_state["current_session_id"] = s_id
                    st.session_state["cuaderno_activo"] = s_cuaderno
                    st.session_state["active_cuaderno"] = s_cuaderno
                    st.session_state["messages"] = cargar_mensajes_sesion(s_id)
                    st.session_state["active_view"] = "chat"
                    st.session_state.audio_text_to_speak = ""
                    st.rerun()
                    
                if es_hilo_actual:
                    st.markdown('</div>', unsafe_allow_html=True)

            with col_th_kebab:
                with st.popover("···", use_container_width=True):
                    st.markdown("<p style='font-size:0.68rem; color:#8A99A8; font-weight:700; text-transform:uppercase;'>Acciones de Hilo</p>", unsafe_allow_html=True)
                    if st.button("🔗 Compartir conversación", key=f"sh_{s_id}", use_container_width=True):
                        st.toast("Enlace copiado al portapapeles.")
                    if st.button("📌 Fijar al inicio", key=f"pin_{s_id}", use_container_width=True):
                        st.toast("Hilo fijado.")
                    if st.button("✏️ Cambiar nombre", key=f"ren_{s_id}", use_container_width=True):
                        st.toast("Función renombrar activada.")
                    st.markdown("<div style='border-top: 1px solid rgba(220,164,138,0.2); margin: 3px 0;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ Borrar", key=f"del_h_{s_id}", use_container_width=True):
                        conn_del = sqlite3.connect(DB_FILE)
                        c_del = conn_del.cursor()
                        c_del.execute("DELETE FROM sesiones WHERE session_id = ?", (s_id,))
                        c_del.execute("DELETE FROM chats WHERE session_id = ?", (s_id,))
                        conn_del.commit()
                        conn_del.close()
                        st.session_state.lista_sesiones_recientes = [
                            s for s in st.session_state.lista_sesiones_recientes if s["session_id"] != s_id
                        ]
                        if st.session_state.get("current_session_id") == s_id:
                            st.session_state["messages"] = []
                        st.rerun()

    st.markdown("---")
    st.markdown('<div class="sidebar-config-header">⚙️ CONFIGURACIÓN</div>', unsafe_allow_html=True)
    voz_sintesis = "Tomas (Argentina - Neural)"
    # --- Carga y persistencia de preferencias por usuario ---
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

# Guardar si hubo cambio
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
leer_en_voz_alta = False

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
    st.rerun()
   
# ----------------- CONTROLADOR DE VOZ -----------------
def render_bottom_voice_dock(text_to_speak: str = "", enable_tts: bool = False, voz_nombre: str = "Tomas"):
    es_tomas = "Tomas" in voz_nombre
    texto_seguro = text_to_speak.replace('"', '\\"').replace('\n', ' ').replace('\r', '') if (text_to_speak and enable_tts) else ""
    
    dock_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ margin: 0; padding: 0; background: transparent; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        .dock-container {{ display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 2px 4px; }}
        .btn-dock {{ background-color: #242D33; color: #DCA48A; border: 1px solid #DCA48A; border-radius: 9999px; padding: 5px 12px; font-size: 0.78rem; font-weight: 700; cursor: pointer; transition: all 0.2s ease; }}
        .btn-dock:hover {{ background-color: #DCA48A; color: #161B1E; }}
        .btn-mute {{ border-color: #ef4444 !important; color: #ef4444 !important; }}
        .btn-mute:hover {{ background-color: #ef4444 !important; color: #ffffff !important; }}
        .status-txt {{ color: #8A99A8; font-size: 0.75rem; margin-right: 6px; }}
    </style>
    </head>
    <body>
    <div class="dock-container">
        <span id="voiceStatus" class="status-txt">{'Voz: Tomás (Neural)' if es_tomas else 'Voz: Elena (Neural)'}</span>
        <button id="micDockBtn" class="btn-dock" onclick="toggleDictation()">🎙️ Dictar</button>
        <button id="muteDockBtn" class="btn-dock btn-mute" onclick="stopSpeech()">⏹ Silenciar</button>
    </div>

    <script>
    var isTomas = {str(es_tomas).lower()};
    var shouldSpeak = {str(enable_tts).lower()};
    var textPayload = "{texto_seguro}";

    function stopSpeech() {{
        if (window.speechSynthesis) {{
            window.speechSynthesis.cancel();
        }}
        document.getElementById("voiceStatus").innerText = "Audio silenciado";
    }}

    function findBestNaturalVoice() {{
        var voices = window.speechSynthesis.getVoices();
        var selected = null;
        if (isTomas) {{
            for (var i = 0; i < voices.length; i++) {{
                var v = voices[i];
                var name = v.name.toLowerCase();
                var lang = v.lang.toLowerCase();
                if ((lang.indexOf("es-ar") !== -1 || lang.indexOf("es_ar") !== -1 || lang.indexOf("es") !== -1) &&
                    (name.indexOf("tomas") !== -1 || name.indexOf("diego") !== -1 || name.indexOf("natural") !== -1 || name.indexOf("neural") !== -1)) {{
                    selected = v;
                    break;
                }}
            }}
        }} else {{
            for (var i = 0; i < voices.length; i++) {{
                var v = voices[i];
                var name = v.name.toLowerCase();
                var lang = v.lang.toLowerCase();
                if ((lang.indexOf("es-ar") !== -1 || lang.indexOf("es_ar") !== -1 || lang.indexOf("es") !== -1) &&
                    (name.indexOf("elena") !== -1 || name.indexOf("natural") !== -1 || name.indexOf("neural") !== -1)) {{
                    selected = v;
                    break;
                }}
            }}
        }}
        if (!selected) {{
            for (var i = 0; i < voices.length; i++) {{
                if (voices[i].lang.toLowerCase().indexOf("es") !== -1) {{
                    selected = voices[i];
                    break;
                }}
            }}
        }}
        return selected;
    }}

    function speakNow() {{
        if (!window.speechSynthesis || !shouldSpeak || textPayload.trim() === "") return;
        window.speechSynthesis.cancel();
        var utterance = new SpeechSynthesisUtterance(textPayload);
        utterance.lang = 'es-AR';
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        var v = findBestNaturalVoice();
        if (v) {{ utterance.voice = v; }}
        utterance.onstart = function() {{ document.getElementById("voiceStatus").innerText = "Hablando..."; }};
        utterance.onend = function() {{ document.getElementById("voiceStatus").innerText = "Listo"; }};
        window.speechSynthesis.speak(utterance);
    }}

    if (window.speechSynthesis) {{
        if (window.speechSynthesis.onvoiceschanged !== undefined) {{
            window.speechSynthesis.onvoiceschanged = speakNow;
        }}
        setTimeout(speakNow, 200);
    }}

    var recognizer = null;
    var recordingActive = false;

    function toggleDictation() {{
        var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {{ alert("Su navegador no soporta dictado por voz. Utilice Google Chrome o Edge."); return; }}
        if (recordingActive && recognizer) {{ recognizer.stop(); return; }}

        recognizer = new SR();
        recognizer.lang = 'es-AR';
        recognizer.continuous = true;
        recognizer.interimResults = true;

        recognizer.onstart = function() {{
            recordingActive = true;
            document.getElementById("micDockBtn").innerText = "🔴 Grabando...";
            document.getElementById("micDockBtn").style.backgroundColor = "#ef4444";
            document.getElementById("micDockBtn").style.color = "#ffffff";
            document.getElementById("voiceStatus").innerText = "Escuchando...";
        }};

        recognizer.onresult = function(event) {{
            var text = '';
            for (var i = event.resultIndex; i < event.results.length; ++i) {{
                if (event.results[i].isFinal) {{ text += event.results[i][0].transcript + ' '; }}
            }}
            if (text.trim() !== "") {{
                var inputs = window.parent.document.querySelectorAll('input[type="text"]');
                for (var j = inputs.length - 1; j >= 0; j--) {{
                    var inp = inputs[j];
                    if (inp.placeholder && inp.placeholder.indexOf("Escribir consulta") !== -1) {{
                        var prev = inp.value ? inp.value + " " : "";
                        inp.value = prev + text.trim();
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        break;
                    }}
                }}
            }}
        }};

        recognizer.onerror = function() {{
            recordingActive = false;
            document.getElementById("micDockBtn").innerText = "🎙️ Dictar";
            document.getElementById("micDockBtn").style.backgroundColor = "#242D33";
            document.getElementById("micDockBtn").style.color = "#DCA48A";
            document.getElementById("voiceStatus").innerText = "En espera";
        }};

        recognizer.onend = function() {{
            recordingActive = false;
            document.getElementById("micDockBtn").innerText = "🎙️ Dictar";
            document.getElementById("micDockBtn").style.backgroundColor = "#242D33";
            document.getElementById("micDockBtn").style.color = "#DCA48A";
            document.getElementById("voiceStatus").innerText = "Dictado finalizado";
        }};

        recognizer.start();
    }}
    </script>
    </body>
    </html>
    """
    components.html(dock_html, height=36)

# ----------------- ÁREA PRINCIPAL -----------------
vista = st.session_state.get("active_view", "chat")

if vista == "chat":
    email_sesion = st.session_state.get("usuario_email", "").lower()
    if "gail" in email_sesion:
        user_name = "GAIL"
    elif "campos" in email_sesion:
        user_name = "DR. CAMPOS"
    else:
        user_name = "DRA. MARTIN"
    alias_display = alias_ia.upper() if alias_ia else "CHRONN"
    has_messages = len(st.session_state["messages"]) > 0
    act_cuad = st.session_state.get("cuaderno_activo", "General").upper()
    sess_id = st.session_state.get("current_session_id", "")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT titulo FROM sesiones WHERE session_id = ?", (sess_id,))
    row_sesion = c.fetchone()
    conn.close()

    titulo_chat_activo = row_sesion[0] if (row_sesion and row_sesion[0]) else "NUEVA CONVERSACIÓN"

    # Panel de Fuentes
    with st.expander("📁 Agregar fuentes y documentos al cuaderno actual"):
        archivo_subido = st.file_uploader("Subir archivos (PDF, TXT, Imágenes, Audio):", type=["png", "jpg", "jpeg", "pdf", "txt", "wav", "mp3"])
        if archivo_subido:
            nombre_archivo = archivo_subido.name
            if act_cuad not in st.session_state.fuentes_cuadernos:
                st.session_state.fuentes_cuadernos[act_cuad] = []
            if nombre_archivo not in st.session_state.fuentes_cuadernos[act_cuad]:
                st.session_state.fuentes_cuadernos[act_cuad].append(nombre_archivo)
                st.success(f"Archivo '{nombre_archivo}' vinculado al cuaderno '{act_cuad}'.")

        fuentes_actuales = st.session_state.fuentes_cuadernos.get(act_cuad, [])
        st.write(f"**Fuentes activas en este cuaderno:** {', '.join(fuentes_actuales) if fuentes_actuales else 'Ninguna'}")

    # Hero State
    if not has_messages:
        st.markdown(f"""
            <div class="hero-empty-container">
                <h1 class="greeting-header">¿En qué puedo ayudarte hoy, <span class="greeting-name">{user_name}</span>?</h1>
                <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
                    <span class="badge-pill-selector">⚙️ {perfil_seleccionado}</span>
                    <span class="badge-pill-selector">🧠 {alias_display}</span>
                    <span class="badge-pill-selector">📁 {act_cuad}</span>
                    <span class="badge-pill-selector">🎙️ {voz_sintesis.split('(')[0].strip()}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    # Mensajes
    if has_messages:
        st.markdown(f"<div style='display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid rgba(220, 164, 138, 0.2); padding-bottom: 10px; margin-bottom: 20px;'><span class='chat-active-header-title'>{act_cuad}: {titulo_chat_activo.upper()}</span><span style='color: #8A99A8; font-size: 0.8rem; font-family: \"Times New Roman\", Times, serif;'>Modo: {perfil_seleccionado} | {alias_display} | Voz: {voz_sintesis}</span></div>", unsafe_allow_html=True)

        for msg in st.session_state["messages"]:
            with st.chat_message(msg["role"], avatar=None):
                if msg["role"] == "user":
                    st.markdown(f"<span class='msg-header-user'>{user_name}:</span>\n\n{msg['content']}", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span class='msg-header-assistant'>{alias_display}:</span>\n\n{msg['content']}", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    st.session_state.audio_text_to_speak = ""

    # Cápsula unificada interactiva estilo Gemini
    col_plus, col_input, col_model, col_mic = st.columns([0.06, 0.70, 0.14, 0.10])

    with col_plus:
        with st.popover("➕", use_container_width=True):
            st.caption("Adjuntar y Herramientas")
            archivo_subido = st.file_uploader("📎 Subir archivos", key="uploader_pill", label_visibility="collapsed")
            if archivo_subido is not None:
                st.success(f"Cargado: {archivo_subido.name}")
            if st.button("📁 Agregar desde Drive", use_container_width=True):
                st.info("Conexión con Drive en desarrollo.")
            st.divider()
            if st.button("🎨 Crear imagen", key="pill_crear_img", use_container_width=True):
                st.session_state["active_view"] = "imagenes"
                st.rerun()
            if st.button("🎬 Crear video", key="pill_crear_vid", use_container_width=True):
                st.session_state["active_view"] = "videos"
                st.rerun()
            if st.button("🎵 Crear música", key="pill_crear_musica", use_container_width=True):
                st.session_state["active_view"] = "musica"
                st.rerun()

    # Selector de modelo
    modelo_actual = st.session_state.get("modelo_ia_seleccionado", "Flash")
    with st.popover(f"{modelo_actual} ▾", use_container_width=True):
        st.caption("Seleccionar Motor IA")
        if st.button("⚡ 3.5 Flash-Lite", use_container_width=True):
            st.session_state["modelo_ia_seleccionado"] = "Flash-Lite"
            st.rerun()
        if st.button("✨ 3.8 Flash", use_container_width=True):
            st.session_state["modelo_ia_seleccionado"] = "Flash"
            st.rerun()
        if st.button("🧠 3.1 Pro", use_container_width=True):
            st.session_state["modelo_ia_seleccionado"] = "Pro"
            st.rerun()
        if st.button("📜 Claude Haiku", use_container_width=True):
            st.session_state["modelo_ia_seleccionado"] = "Haiku"
            st.rerun()

    # Input principal libre para habilitar el envío
    user_prompt = st.chat_input(f"Preguntarle a {alias_display}...")
    user_prompt = st.chat_input(f"Preguntarle a {alias_display}...")
with col_mic:
        import streamlit.components.v1 as _components
        _components.html("""
        <div style="display: flex; gap: 6px; align-items: center; justify-content: center; height: 100%;">
            <button id="micBtn" style="background: #242D33; border: 1px solid #DCA48A; color: #DCA48A; border-radius: 8px; width: 38px; height: 38px; cursor: pointer; font-size: 16px; display: flex; align-items: center; justify-content: center;" title="Iniciar Dictado">🎙️</button>
            <button id="stopBtn" style="background: #242D33; border: 1px solid #ef4444; color: #ef4444; border-radius: 8px; width: 38px; height: 38px; cursor: pointer; font-size: 16px; display: flex; align-items: center; justify-content: center;" title="Detener">⏹️</button>
        </div>

        <script>
        let recognizer = null;
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (SpeechRec) {
            recognizer = new SpeechRec();
            recognizer.lang = 'es-AR';
            recognizer.continuous = true;
            recognizer.interimResults = false;

            recognizer.onresult = (e) => {
                let texto = '';
                for (let i = e.resultIndex; i < e.results.length; ++i) {
                    if (e.results[i].isFinal) texto += e.results[i][0].transcript;
                }
                const parentDoc = window.parent.document;
                const txtArea = parentDoc.querySelector('textarea[data-testid="stChatInputTextArea"]');
                if (txtArea && texto) {
                    txtArea.value = (txtArea.value ? txtArea.value + ' ' : '') + texto;
                    txtArea.dispatchEvent(new Event('input', { bubbles: true }));
                }
            };

            recognizer.onerror = (e) => console.log('Error de voz:', e.error);
        }

        const micBtn = document.getElementById('micBtn');
        const stopBtn = document.getElementById('stopBtn');

        micBtn.onclick = () => {
            if (recognizer) {
                try {
                    recognizer.start();
                    micBtn.style.background = '#DCA48A';
                    micBtn.style.color = '#161B1E';
                } catch(err) { console.log(err); }
            }
        };

        stopBtn.onclick = () => {
            if (recognizer) {
                try {
                    recognizer.stop();
                } catch(err) {}
            }
            micBtn.style.background = '#242D33';
            micBtn.style.color = '#DCA48A';
            window.parent.speechSynthesis.cancel();
        };
        </script>
        """, height=45)

# Procesamiento del mensaje con autodetección de modelos
if user_prompt and user_prompt.strip():
    prompt = user_prompt.strip()
    act_cuad = st.session_state.get("cuaderno_activo", "General")
    sess_id = st.session_state.get("current_session_id")

    titulo_limpio = prompt.replace("\n", " ")
    titulo_calculado = (titulo_limpio[:28] + "..") if len(titulo_limpio) > 28 else titulo_limpio

    crear_o_actualizar_sesion_db(sess_id, prompt, act_cuad)
    guardar_mensaje_db(sess_id, "user", prompt, act_cuad)

    st.session_state.lista_sesiones_recientes = [
            s for s in st.session_state.lista_sesiones_recientes if s["session_id"] != sess_id
    ]

    nueva_entrada = {
        "session_id": sess_id,
        "titulo": titulo_calculado,
        "cuaderno": act_cuad,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    st.session_state.lista_sesiones_recientes.insert(0, nueva_entrada)
    st.session_state.messages.append({"role": "user", "content": prompt})
    try:
        if anthropic and CLAUDE_API_KEY and not CLAUDE_API_KEY.startswith("TU_CLAVE"):
            client = anthropic.Anthropic(api_key=CLAUDE_API_KEY.strip())
            fuentes_list = st.session_state.fuentes_cuadernos.get(act_cuad, [])
            system_prompt = (
                f"{PROMPTS_POR_PERFIL[perfil_seleccionado]}\n\n"
                f"Estás operando en el cuaderno web '{act_cuad}' "
                f"con las fuentes: {', '.join(fuentes_list) if fuentes_list else 'Ninguna'}."
            )

            # Autodescubrimiento dinámico de modelos asignados a la clave
            modelos_disponibles = []
            try:
                resp_models = client.models.list()
                if hasattr(resp_models, 'data') and resp_models.data:
                    modelos_disponibles = [m.id for m in resp_models.data if getattr(m, 'id', '')]
            except Exception:
                pass

            # Prioridad de inferencia (Sonnet 3.5 -> Haiku -> Opus)
            candidatos = [
                "claude-3-5-sonnet-latest",
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-latest",
                "claude-3-5-haiku-20241022",
                "claude-3-haiku-20240307",
                "claude-3-opus-20240229"
            ]

            # Si la API devolvió lista de modelos, los priorizamos
            lista_final = modelos_disponibles + [c for c in candidatos if c not in modelos_disponibles]

            exito = False
            ultimo_err = None

            for mod in lista_final:
                try:
                    stream = client.messages.create(
                        model=mod,
                        max_tokens=1500,
                        system=system_prompt,
                        messages=[{"role": "user", "content": prompt}],
                        stream=True
                    )

                    for event in stream:
                        if hasattr(event, 'type') and event.type == 'content_block_delta':
                            if hasattr(event.delta, 'text'):
                                chunk = event.delta.text
                                respuesta_completa += chunk
                                contenedor_respuesta.markdown(respuesta_completa + "▌")

                        contenedor_respuesta.markdown(respuesta_completa)
                    exito = True
                    break
                except Exception as e_mod:
                    ultimo_err = e_mod
                    # Si es 404 de modelo, prueba automáticamente el siguiente
                    if "404" in str(e_mod) or "not_found_error" in str(e_mod):
                        continue
                    else:
                        raise e_mod

            if not exito:
                if modelos_disponibles:
                    msg_diag = f"Modelos detectados en su cuenta: {', '.join(modelos_disponibles)}."
                else:
                    msg_diag = "Anthropic aún no ha propagado los endpoints de inferencia para esta clave."
                respuesta_completa = (
                    f"Aviso de infraestructura: {msg_diag}\n\n"
                    "Si recién acreditó el saldo de $16 USD, Anthropic suele demorar entre 5 y 15 minutos "
                    "en autorizar los servidores de procesamiento. En breve quedará activo automáticamente."
                )
                contenedor_respuesta.markdown(respuesta_completa)

        else:
            respuesta_completa = f"Estimada/o ({st.session_state.usuario_email}), le saludo desde la versión web de JUXALEGIS OS en el cuaderno [{act_cuad}]. Su consulta fue procesada exitosamente."
            contenedor_respuesta.markdown(respuesta_completa)

    except Exception as e:
        respuesta_completa = f"Error al procesar la solicitud con la API: {str(e)}"
        contenedor_respuesta.markdown(respuesta_completa)

    guardar_mensaje_db(sess_id, "assistant", respuesta_completa, act_cuad)
    st.session_state["messages"].append({"role": "assistant", "content": respuesta_completa})
    if leer_en_voz_alta:
        st.session_state.audio_text_to_speak = respuesta_completa
    else:
        st.session_state.audio_text_to_speak = ""
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

elif vista == "ver_cuaderno":
    cuaderno = st.session_state.get("active_cuaderno", "General")
    col_head_1, col_head_2 = st.columns([0.7, 0.3])
    with col_head_1:
        st.markdown(f'<div class="expediente-title-serif">EXPEDIENTE: {cuaderno}</div>', unsafe_allow_html=True)
    with col_head_2:
        if st.button("➕ Nuevo Hilo en este Cuaderno", use_container_width=True):
            st.session_state["current_session_id"] = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            st.session_state["messages"] = []
            st.session_state["cuaderno_activo"] = cuaderno
            st.session_state["active_cuaderno"] = cuaderno
            st.session_state["active_view"] = "chat"
            st.rerun()

    st.markdown("<p style='font-size: 0.85rem; color: #8A99A8; font-weight: bold;'>HILOS DE TRABAJO ASOCIADOS:</p>", unsafe_allow_html=True)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT session_id, titulo, ultima_actividad FROM sesiones WHERE cuaderno = ? ORDER BY ultima_actividad DESC", (cuaderno,))
    hilos_cuaderno = c.fetchall()
    conn.close()

    if hilos_cuaderno:
        for s_id, s_tit, s_act in hilos_cuaderno:
            col_h1, col_h2 = st.columns([0.8, 0.2])
            with col_h1:
                titulo_hilo = s_tit if s_tit else "Conversación"
                st.markdown(f"**💬 {titulo_hilo}** <span style='font-size:0.75rem; color:#8A99A8;'>({s_act})</span>", unsafe_allow_html=True)
            with col_h2:
                if st.button("Continuar", key=f"cont_{s_id}", use_container_width=True):
                    st.session_state["current_session_id"] = s_id
                    st.session_state["cuaderno_activo"] = cuaderno
                    st.session_state["active_cuaderno"] = cuaderno
                    st.session_state["messages"] = cargar_mensajes_sesion(s_id)
                    st.session_state["active_view"] = "chat"
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
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO cuadernos (nombre) VALUES (?)", (nuevo_nomb.strip(),))
                        conn.commit()
                    except sqlite3.IntegrityError:
                        pass
                    conn.close()
                    if nuevo_nomb.strip() not in st.session_state.fuentes_cuadernos:
                        st.session_state.fuentes_cuadernos[nuevo_nomb.strip()] = []
                    st.session_state["active_cuaderno"] = nuevo_nomb.strip()
                    st.session_state["cuaderno_activo"] = nuevo_nomb.strip()
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
        st.info("No hay cuadernos activos. Pulse '+ Nuevo cuaderno' para registrar un expediente.")
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
