from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import calendar
import hmac
import json
import os
import time
import holidays
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# En PythonAnywhere el directorio de trabajo no es el del proyecto: usar rutas absolutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DATA_DIR permite guardar los datos fuera del código (volumen persistente en Docker/PaaS)
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
ARCHIVO_TURNOS = os.path.join(DATA_DIR, 'turnos.json')
ARCHIVO_NOTAS = os.path.join(DATA_DIR, 'notas.json')
ARCHIVO_CLAVE = os.path.join(DATA_DIR, 'clave.json')

# Se definen como variables de entorno (en PythonAnywhere: archivo WSGI), nunca en el código
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
MAX_NOTA = 1000

def cargar_secret_key():
    # Sin SECRET_KEY en el entorno se genera una y se guarda: con varios procesos, una clave al azar por proceso rompe las sesiones
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    ruta = os.path.join(DATA_DIR, '.secret_key')
    if not os.path.exists(ruta):
        fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(os.urandom(32).hex())
    with open(ruta) as f:
        return f.read().strip()

app.secret_key = cargar_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("APP_HTTPS") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
    MAX_CONTENT_LENGTH=64 * 1024,
)

@app.after_request
def cabeceras_seguridad(resp):
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    return resp

def escribir_json(ruta, datos):
    # Escribe en un temporal y reemplaza: evita archivos a medias si dos peticiones guardan a la vez
    tmp = f"{ruta}.{os.getpid()}.tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ruta)

def anio_mes_desde_url():
    # Valores inválidos en la URL (mes=13, anio=abc...) vuelven al mes actual en vez de dar error 500
    hoy = datetime.today()
    try:
        anio = int(request.args.get("anio", hoy.year))
        mes = int(request.args.get("mes", hoy.month))
    except ValueError:
        return hoy.year, hoy.month
    if not (1900 <= anio <= 2100 and 1 <= mes <= 12):
        return hoy.year, hoy.month
    return anio, mes

# Bloqueo simple contra fuerza bruta: 5 fallos seguidos = 60 s de espera
intentos_fallidos = {"n": 0, "hasta": 0.0}

def hash_guardado():
    # Una vez cambiada desde la app, la contraseña vive aquí (hash) y APP_PASSWORD deja de usarse
    if os.path.exists(ARCHIVO_CLAVE):
        with open(ARCHIVO_CLAVE, 'r') as f:
            try:
                return json.load(f).get("hash", "")
            except ValueError:
                pass
    return ""

def clave_correcta(clave):
    h = hash_guardado()
    if h:
        return check_password_hash(h, clave)
    return bool(APP_PASSWORD) and hmac.compare_digest(clave.encode(), APP_PASSWORD.encode())

def version_clave():
    # Cambia al cambiar la contraseña: invalida las sesiones abiertas en otros dispositivos
    return hash_guardado()[-16:] or "env"

@app.before_request
def exigir_login():
    if request.endpoint in ("login", "static"):
        return None
    if session.get("autenticado") and session.get("v") == version_clave():
        return None
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if time.time() < intentos_fallidos["hasta"]:
            error = "Demasiados intentos. Espera un minuto."
        elif clave_correcta(request.form.get("password", "")):
            intentos_fallidos["n"] = 0
            session.clear()
            session["autenticado"] = True
            session["v"] = version_clave()
            session.permanent = True
            return redirect(url_for("index"))
        else:
            intentos_fallidos["n"] += 1
            if intentos_fallidos["n"] >= 5:
                intentos_fallidos.update(n=0, hasta=time.time() + 60)
            error = "Contraseña incorrecta."
    return render_template("login.html", error=error)

@app.route("/clave", methods=["GET", "POST"])
def cambiar_clave():
    error = ok = None
    if request.method == "POST":
        nueva = request.form.get("nueva", "")
        if not clave_correcta(request.form.get("actual", "")):
            error = "La contraseña actual no es correcta."
        elif len(nueva) < 8:
            error = "La nueva contraseña debe tener al menos 8 caracteres."
        elif nueva != request.form.get("repetir", ""):
            error = "Las contraseñas nuevas no coinciden."
        else:
            escribir_json(ARCHIVO_CLAVE, {"hash": generate_password_hash(nueva)})
            session["v"] = version_clave()
            ok = "Contraseña actualizada."
    return render_template("clave.html", error=error, ok=ok)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

# Secuencia exacta: 7 Día, 7 Descanso = 14 días en total
PATRON = (["D"] * 7) + (["Desc"] * 7)

# Nombres en español fijos para evitar problemas con el idioma del sistema operativo
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

def cargar_configuracion():
    # Carga la fecha guardada para que no se borre si apagas la PC
    if os.path.exists(ARCHIVO_TURNOS):
        with open(ARCHIVO_TURNOS, 'r') as f:
            try:
                data = json.load(f)
                if data.get('fecha_inicio'):
                    return datetime.strptime(data['fecha_inicio'], "%Y-%m-%d")
            except (ValueError, OSError):
                pass
    return None

def guardar_configuracion(fecha_str):
    escribir_json(ARCHIVO_TURNOS, {'fecha_inicio': fecha_str})

def cargar_notas():
    # Formato: {"AAAA-MM-DD": "texto"}
    if os.path.exists(ARCHIVO_NOTAS):
        with open(ARCHIVO_NOTAS, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except ValueError:
                pass
    return {}

def guardar_notas(notas):
    escribir_json(ARCHIVO_NOTAS, notas)

def obtener_turno(fecha_consulta, fecha_inicio):
    if not fecha_inicio:
        return None
    diferencia = (fecha_consulta - fecha_inicio).days
    if diferencia < 0:
        return None # Fechas anteriores al primer turno no tienen color
    # El residuo de dividir entre el largo del patrón da la posición exacta en el ciclo
    return PATRON[diferencia % len(PATRON)]

@app.route("/", methods=["GET", "POST"])
def index():
    anio, mes = anio_mes_desde_url()

    # Manejar el formulario de configuración
    if request.method == "POST":
        if "resetear" in request.form:
            guardar_configuracion(None)
        else:
            fecha_str = request.form.get("fecha_inicio", "")
            try:
                datetime.strptime(fecha_str, "%Y-%m-%d")
                guardar_configuracion(fecha_str)
            except ValueError:
                pass
        return redirect(url_for("index", anio=anio, mes=mes))

    fecha_inicio = cargar_configuracion()
    notas = cargar_notas()

    # Generar la cuadrícula del mes
    cal = calendar.Calendar(firstweekday=0) # 0 = El calendario empieza en Lunes
    semanas = cal.monthdatescalendar(anio, mes)
    # Feriados de Chile (incluye los traslados a lunes/viernes según la ley vigente)
    feriados = holidays.Chile(years={anio - 1, anio, anio + 1}, language="es")

    calendario_datos = []
    for semana in semanas:
        semana_datos = []
        for dia in semana:
            es_mes_actual = dia.month == mes
            tipo_turno = None
            if es_mes_actual and fecha_inicio:
                fecha_dt = datetime(dia.year, dia.month, dia.day)
                tipo_turno = obtener_turno(fecha_dt, fecha_inicio)

            semana_datos.append({
                "dia": dia.day,
                "fecha": dia.isoformat(),
                "nota": notas.get(dia.isoformat(), "") if es_mes_actual else "",
                "es_mes_actual": es_mes_actual,
                "turno": tipo_turno,
                "feriado": feriados.get(dia) if es_mes_actual else None
            })
        calendario_datos.append(semana_datos)

    # Lógica para los botones de Siguiente / Anterior mes
    mes_ant = mes - 1 if mes > 1 else 12
    anio_ant = anio if mes > 1 else anio - 1
    mes_sig = mes + 1 if mes < 12 else 1
    anio_sig = anio if mes < 12 else anio + 1

    return render_template(
        "calendario.html",
        anio=anio,
        mes=mes,
        mes_nombre=MESES[mes-1],
        calendario=calendario_datos,
        fecha_inicio=fecha_inicio.strftime("%Y-%m-%d") if fecha_inicio else None,
        mes_ant=mes_ant, anio_ant=anio_ant,
        mes_sig=mes_sig, anio_sig=anio_sig
    )

@app.route("/nota", methods=["POST"])
def guardar_nota():
    fecha = request.form.get("fecha", "")
    texto = "" if "borrar" in request.form else request.form.get("texto", "").strip()[:MAX_NOTA]
    destino = request.form.get("destino", "index")
    try:
        d = datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        return redirect(url_for("index"))

    notas = cargar_notas()
    if texto:
        notas[fecha] = texto
    else:
        notas.pop(fecha, None)
    guardar_notas(notas)
    if destino == "notas":
        return redirect(url_for("ver_notas", anio=d.year, mes=d.month))
    return redirect(url_for("index", anio=d.year, mes=d.month))

@app.route("/notas")
def ver_notas():
    anio, mes = anio_mes_desde_url()
    prefijo = f"{anio:04d}-{mes:02d}-"
    lista = [
        {"fecha": f, "dia": int(f[-2:]), "texto": t}
        for f, t in sorted(cargar_notas().items()) if f.startswith(prefijo)
    ]
    mes_ant = mes - 1 if mes > 1 else 12
    anio_ant = anio if mes > 1 else anio - 1
    mes_sig = mes + 1 if mes < 12 else 1
    anio_sig = anio if mes < 12 else anio + 1
    return render_template(
        "notas.html", anio=anio, mes=mes, mes_nombre=MESES[mes-1], notas=lista,
        mes_ant=mes_ant, anio_ant=anio_ant, mes_sig=mes_sig, anio_sig=anio_sig
    )

if __name__ == "__main__":
    # Solo para desarrollo local; en producción lo sirve el hosting (WSGI)
    app.run(debug=os.environ.get("APP_DEBUG") == "1", host=os.environ.get("APP_HOST", "127.0.0.1"))