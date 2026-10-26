# Despliegue de Turnos Básicos

Aplicación Flask (Python 3.9+). Los datos se guardan en archivos JSON, sin base de datos.

## 1. Antes de desplegar (común a todos los sitios)

### Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `APP_PASSWORD` | Sí (primer acceso) | Contraseña inicial. Sin ella y sin `clave.json`, nadie puede entrar. |
| `SECRET_KEY` | Recomendada | Texto largo aleatorio para firmar sesiones. Si falta, se genera y guarda en `.secret_key`. |
| `APP_HTTPS` | Recomendada | `1` si el sitio usa HTTPS (cookie solo por HTTPS). No usar en local con `http://`. |
| `DATA_DIR` | Opcional | Carpeta donde se guardan `turnos.json`, `notas.json`, `clave.json` y `.secret_key`. Por defecto, la carpeta del proyecto. |

Generar una `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Archivos que NO deben subirse a git

El `.gitignore` ya excluye `.venv/`, `__pycache__/`, `turnos.json`, `notas.json`, `clave.json` y `.secret_key`.

Si `.venv/` o `turnos.json` ya estaban en git, el `.gitignore` no los quita del historial. Para dejar de rastrearlos:

```bash
git rm -r --cached .venv .venv-1 __pycache__ turnos.json
git commit -m "Dejar de versionar entorno virtual y datos"
```

Si el repositorio es público, las notas pasadas ya subidas siguen en el historial.

### Probar en local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
APP_PASSWORD="prueba123" python3 app.py
# abrir http://127.0.0.1:5000
```

Para verla desde el celular en la misma WiFi: `APP_HOST=0.0.0.0` (solo en red de confianza). `APP_DEBUG=1` activa el modo depuración; nunca en producción.

### Requisitos que debe cumplir el hosting

- Python 3.9 o superior con WSGI.
- Una carpeta con escritura persistente para los JSON.
- HTTPS.

---

## 2. PythonAnywhere (cuenta gratuita)

1. Abre una consola **Bash** y clona el proyecto (reemplaza la URL):

   ```bash
   git clone https://github.com/TU_USUARIO/turnosBasicos.git
   cd turnosBasicos
   mkvirtualenv --python=python3.10 turnos
   pip install -r requirements.txt
   ```

2. Pestaña **Web** > **Add a new web app** > **Manual configuration** > Python 3.10.
3. En **Virtualenv** escribe `/home/TU_USUARIO/.virtualenvs/turnos`.
4. En **WSGI configuration file**, reemplaza todo el contenido por:

   ```python
   import os, sys

   ruta = "/home/TU_USUARIO/turnosBasicos"
   if ruta not in sys.path:
       sys.path.insert(0, ruta)

   os.environ["APP_PASSWORD"] = "una-clave-larga"
   os.environ["SECRET_KEY"] = "texto-largo-aleatorio"
   os.environ["APP_HTTPS"] = "1"

   from app import app as application
   ```

5. Activa **Force HTTPS** y pulsa **Reload**.
6. Abre `https://TU_USUARIO.pythonanywhere.com`.

Importante en la cuenta gratuita:

- La app se desactiva si no pulsas **Run until 3 months from today** en la pestaña **Web** cada cierto tiempo. PythonAnywhere avisa por correo antes.
- Solo hay una app y el dominio es `usuario.pythonanywhere.com`.
- Para actualizar: `cd ~/turnosBasicos && git pull`, luego **Reload**.

---

## 3. Hosting con cPanel (Hostnet, HostGator, etc.)

Requiere que el plan incluya **Setup Python App** (CloudLinux + Passenger). Si no aparece en tu cPanel, tu plan no soporta Python y tendrás que pedir al soporte que lo active o usar otra opción (PythonAnywhere o un VPS).

> Hostinger usa hPanel, no cPanel, y sus planes compartidos no ejecutan Python. Para Hostinger necesitas un VPS (ver sección 4).

1. **Subir el código** a una carpeta **fuera** de `public_html`, por ejemplo `/home/USUARIO/turnos`. Opciones:
   - **Administrador de archivos**: subir un zip y extraerlo.
   - **Git Version Control** de cPanel, clonando el repositorio.
   Esto evita que Apache sirva directamente `turnos.json`, `notas.json` o `clave.json`.
2. cPanel > **Setup Python App** > **Create Application**:
   - Python version: 3.9 o superior.
   - Application root: `turnos`
   - Application URL: el dominio o subdominio (por ejemplo `turnos.midominio.cl`)
   - Application startup file: `passenger_wsgi.py`
   - Application Entry point: `application`
3. En **Environment variables** agrega `APP_PASSWORD`, `SECRET_KEY` y `APP_HTTPS=1`.
4. En **Configuration files** escribe `requirements.txt` > **Add** > **Run Pip Install**.
5. Activa HTTPS en **SSL/TLS Status** (AutoSSL) y pulsa **Restart** en la app.
6. Abre la URL y entra con `APP_PASSWORD`.

Notas:

- Después de cada cambio de código o de variables, pulsa **Restart**.
- Si aparece un error 500, revisa `stderr.log` en la carpeta de la app o el **Registro de errores** de cPanel.
- Si el hosting reasigna el entorno virtual, el comando `source /home/USUARIO/virtualenv/turnos/3.x/bin/activate` aparece arriba en la página de la app.

---

## 4. VPS propio (Ubuntu/Debian) con gunicorn + nginx

```bash
sudo apt install python3-venv nginx
sudo adduser --system --group turnos
sudo -u turnos git clone https://github.com/TU_USUARIO/turnosBasicos.git /opt/turnos
cd /opt/turnos
sudo -u turnos python3 -m venv .venv
sudo -u turnos .venv/bin/pip install -r requirements.txt gunicorn
```

Archivo de variables `/etc/turnos.env` (permisos `600`, dueño root):

```
APP_PASSWORD=una-clave-larga
SECRET_KEY=texto-largo-aleatorio
APP_HTTPS=1
DATA_DIR=/var/lib/turnos
```

```bash
sudo mkdir /var/lib/turnos && sudo chown turnos: /var/lib/turnos
```

`/etc/systemd/system/turnos.service`:

```ini
[Unit]
Description=Turnos Basicos
After=network.target

[Service]
User=turnos
WorkingDirectory=/opt/turnos
EnvironmentFile=/etc/turnos.env
ExecStart=/opt/turnos/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now turnos
```

`/etc/nginx/sites-available/turnos`:

```nginx
server {
    server_name turnos.midominio.cl;
    client_max_body_size 64k;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/turnos /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx -d turnos.midominio.cl
```

---

## 5. Docker / plataformas tipo Render, Railway, Fly.io

Estas plataformas borran el disco en cada despliegue. **Sin un volumen persistente perderás notas, turnos y contraseña.**

`Dockerfile` de ejemplo:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
ENV DATA_DIR=/data
VOLUME /data
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:app"]
```

```bash
docker build -t turnos .
docker run -d -p 8000:8000 -v turnos_data:/data \
  -e APP_PASSWORD=una-clave-larga -e SECRET_KEY=texto-largo-aleatorio -e APP_HTTPS=1 \
  turnos
```

En Render, Railway o Fly.io: crea un volumen/disk montado en `/data`, define las mismas variables y usa el comando `gunicorn -w 2 -b 0.0.0.0:$PORT app:app`.

---

## 6. Después de desplegar

- [ ] Entrar sin sesión a `/` redirige a `/login`.
- [ ] Probar una contraseña mala y luego la correcta.
- [ ] Crear, editar y borrar una nota; aplicar y resetear los turnos.
- [ ] Cambiar la contraseña desde la app y volver a entrar.
- [ ] Confirmar que `https://tu-sitio/turnos.json` y `/notas.json` dan 404.
- [ ] Cerrar sesión y verificar que `/notas` vuelve a pedir contraseña.

## 7. Respaldos y recuperación

- **Respaldo**: copiar `turnos.json`, `notas.json` y `clave.json` (en `DATA_DIR`) cada cierto tiempo.
- **Olvidé la contraseña**: borrar `clave.json`; vuelve a valer `APP_PASSWORD`.
- **Cerrar todas las sesiones**: cambiar `SECRET_KEY` y reiniciar.

## 8. Limitaciones conocidas

- Es para una sola persona o grupo con una sola contraseña, sin usuarios individuales.
- Los datos son globales: todos los que conozcan la contraseña ven las mismas notas y los mismos turnos.
- El bloqueo por intentos fallidos (5 fallos = 60 s) es global y vive en memoria de cada proceso.
