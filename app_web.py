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
    nombres_mock_cuadernos = ['PRUEBE 0', 'PRUEBA', 'HOLA', 'GENERAL', 'PRUEBA 3', 'General', 'prueba 3']
    placeholders = ','.join('?' for _ in nombres_mock_cuadernos)
    c.execute(f"DELETE FROM cuadernos WHERE UPPER(nombre) IN ({placeholders})", 
              [n.upper() for n in nombres_mock_cuadernos])
    
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
