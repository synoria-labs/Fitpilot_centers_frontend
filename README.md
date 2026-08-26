# FitPilot - Sistema de Gestión para Gimnasios

Sistema de gestión integral para gimnasios desarrollado con PySide6 (Qt) y arquitectura MVC, integrado con backend GraphQL/FastAPI.

## 🚀 Características

- **Gestión de Socios**: CRUD completo de miembros, búsqueda avanzada, historial
- **Control de Clases**: Sistema de reservas, control de ocupación, horarios
- **Membresías y Pagos**: Gestión de paquetes, pagos, renovaciones automáticas
- **WhatsApp Integration**: Plantillas, mensajes masivos, comunicación automatizada
- **Dashboard Analítico**: Métricas en tiempo real, gráficas, reportes
- **Arquitectura MVC**: Separación clara de responsabilidades
- **Carga Paralela**: Uso de QThreadPool para operaciones asíncronas
- **Sistema de Cache**: Optimización de rendimiento con cache multinivel

## 📋 Requisitos Previos

- Python 3.12 o superior (probado en 3.14)
- Acceso al backend de FitPilot:
  - **Producción:** `https://webhook.fitpilot.fit`
  - **Local (dev):** backend FastAPI/GraphQL en `http://127.0.0.1:8000`

## 🔧 Instalación

1. **Ubicarse en la carpeta del frontend**
```bash
cd Fitpilot_centers_frontend
```

2. **Crear entorno virtual**
```bash
python -m venv .venv
```

3. **Activar entorno virtual**
```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat

# Linux/Mac
source .venv/bin/activate
```

> **Windows:** si al activar ves *"la ejecución de scripts está deshabilitada en este sistema"*,
> habilita los scripts solo para tu usuario (no requiere admin) y vuelve a activar:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

4. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

> `gql` se instala con el extra **`[websockets]`** (ya declarado en `requirements.txt`). Es **obligatorio**:
> las suscripciones del chat de WhatsApp usan `WebsocketsTransport`. Sin él, la pestaña *Chats* falla
> con `No module named 'websockets'`.

5. **Configurar variables de entorno**
```powershell
# Copiar archivo de ejemplo (ya viene con las URLs de producción)
Copy-Item .env.example .env
```

Ajusta el `.env` según el entorno:

| Variable         | Producción                              | Local (dev)                      |
| ---------------- | --------------------------------------- | -------------------------------- |
| `API_BASE_URL`   | `https://webhook.fitpilot.fit`          | `http://127.0.0.1:8000`          |
| `GRAPHQL_URL`    | `https://webhook.fitpilot.fit/graphql`  | `http://127.0.0.1:8000/graphql`  |
| `GRAPHQL_WS_URL` | `wss://webhook.fitpilot.fit/graphql`    | `ws://127.0.0.1:8000/graphql`    |
| `REST_USERS_URL` | `https://webhook.fitpilot.fit/users`    | `http://127.0.0.1:8000/users`    |
| `ENVIRONMENT`    | `production`                            | `development`                    |

> **Importante:** `ENVIRONMENT` va en **minúscula** (el código compara `== 'production'`). Si dejas
> `GRAPHQL_URL` apuntando a `localhost` en producción, el login fallará con *"All connection attempts failed"*
> (que la app muestra como *"Credenciales inválidas"*).

## 🏃‍♂️ Ejecución

### Modo Desarrollo
```bash
python main.py
```

### Modo Producción
```bash
# Configurar ENVIRONMENT=production en .env
python main.py
```

## 🗂️ Estructura del Proyecto

```
frontend/
├── app/
│   ├── core/           # Configuración, logging, DI
│   ├── auth/           # Autenticación y sesiones
│   ├── graphql/        # Cliente GraphQL
│   ├── services/       # Servicios de negocio
│   ├── models/         # Modelos y DTOs
│   ├── views/          # Vistas Qt (UI)
│   │   └── tabs/       # Pestañas de la aplicación
│   ├── controllers/    # Controladores MVC
│   ├── threads/        # Workers, AsyncioExecutor (event loop dedicado)
│   └── assets/         # Recursos UI (estilos, íconos, logos)
├── main.py            # Punto de entrada
├── requirements.txt   # Dependencias
└── .env              # Configuración local
```

## 🔐 Autenticación

El sistema utiliza JWT con tokens de acceso (15 min) y refresh (7 días):

- **Login inicial**: Email + contraseña
- **Renovación automática**: El token se renueva automáticamente antes de expirar
- **Roles**: admin, recepcionista, usuario
- **Permisos**: Control granular por pestaña y acción

## 📊 Módulos Principales

### Socios
- Listado con búsqueda y filtros
- Creación y edición de miembros
- Historial de pagos y reservas
- Conversión de leads

### Clases
- Vista semanal de ocupación
- Sistema de reservas
- Control de bicicletas
- Check-in de asistencia

### Pagos
- Registro de pagos
- Gestión de paquetes/membresías
- Reportes de ingresos
- Integración con MercadoPago

### WhatsApp
- Plantillas personalizables
- Envío masivo
- Historial de conversaciones
- Automatización de mensajes

### Dashboard
- Métricas en tiempo real
- Gráficas interactivas
- Alertas y notificaciones
- Análisis de tendencias

## 🛠️ Desarrollo

### Ejecutar tests
```bash
pytest tests/
```

### Formateo de código
```bash
black app/
```

### Linting
```bash
flake8 app/
```

## 📈 Performance

- **Carga paralela**: Las pestañas se cargan en threads separados
- **Cache multinivel**: Memoria + disco para datos frecuentes
- **Lazy loading**: Los componentes se cargan bajo demanda
- **Virtualización**: Tablas grandes usan renderizado virtual

## 🐛 Troubleshooting

### `activate.ps1 ... la ejecución de scripts está deshabilitada`
- Política de PowerShell. Ejecuta: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.

### `No module named 'websockets'` (al abrir la pestaña *Chats*)
- Falta el extra de `gql`. Ejecuta `pip install -r requirements.txt` (declara `gql[websockets]`).

### Login falla con *"Credenciales inválidas"* pese a credenciales correctas
- El frontend no alcanza el backend (error real: *"All connection attempts failed"*).
- Revisa `GRAPHQL_URL` en `.env`: en producción debe ser `https://webhook.fitpilot.fit/graphql` (no `localhost`).
- Verifica que la API responde: `curl https://webhook.fitpilot.fit/health` → `{"status":"ok"}`.

### Error de autenticación
- Limpiar sesión: eliminar `data/.session.json`
- Verificar credenciales en el backend

### Problemas de rendimiento
- Limpiar cache: `rm -rf cache/*`
- Aumentar `MAX_THREADS` en config.py

## 🤝 Contribuir

1. Fork del proyecto
2. Crear rama feature (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir Pull Request

## 📝 Licencia

Propiedad de FitPilot. Todos los derechos reservados.

## 📧 Contacto

Para soporte técnico: soporte@fitpilot.com

---

**Versión**: 1.0.0  
**Última actualización**: Junio 2026
