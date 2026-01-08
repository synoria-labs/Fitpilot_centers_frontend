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

- Python 3.9 o superior
- PostgreSQL (backend)
- Backend FastAPI/GraphQL ejecutándose (puerto 8000)

## 🔧 Instalación

1. **Clonar el repositorio** (o descomprimir el proyecto)
```bash
cd C:\Users\ale_o\FitPilot\frontend
```

2. **Crear entorno virtual**
```bash
python -m venv .venv
```

3. **Activar entorno virtual**
```bash
# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

4. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

5. **Configurar variables de entorno**
```bash
# Copiar archivo de ejemplo
copy .env.example .env

# Editar .env con tus configuraciones
notepad .env
```

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
│   ├── threads/        # Workers y procesamiento paralelo
│   └── ui/            # Recursos UI (estilos, íconos)
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

### Error de conexión al backend
- Verificar que el backend esté ejecutándose en http://localhost:8001
- Revisar configuración en `.env`

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
**Última actualización**: Septiembre 2025
