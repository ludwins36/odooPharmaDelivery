# Odoo 17 - Entorno de Desarrollo con Docker

## Estructura del Proyecto

```
odoo17/
├── docker-compose.yml    # Configuración de Docker
├── config/
│   └── odoo.conf         # Configuración de Odoo
├── addons/               # Tus módulos personalizados
│   └── mi_modulo/        # Módulo de ejemplo
└── README.md
```

## Requisitos

- Docker Desktop instalado
- Docker Compose

## Iniciar el Entorno

```bash
# Iniciar los contenedores
docker-compose up -d

# Ver logs en tiempo real
docker-compose logs -f odoo

# Detener los contenedores
docker-compose down
```

## Acceso

- **Odoo**: http://localhost:8069
- **Base de datos PostgreSQL**: localhost:5432
  - Usuario: odoo
  - Contraseña: odoo

## Primera Configuración

1. Accede a http://localhost:8069
2. Crea una nueva base de datos:
   - Master Password: admin
   - Database Name: odoo17
   - Email: tu@email.com
   - Password: tu contraseña
   - Language: Spanish (ES)
   - Country: tu país

## Desarrollo de Módulos

### Crear un nuevo módulo

1. Crea una carpeta en `addons/` con el nombre de tu módulo
2. Agrega los archivos básicos:
   - `__manifest__.py`
   - `__init__.py`
   - `models/`
   - `views/`
   - `security/`

### Actualizar módulos

Después de hacer cambios en tu módulo:

```bash
# Reiniciar Odoo para que detecte cambios
docker-compose restart odoo
```

O desde la interfaz de Odoo:
1. Modo desarrollador: Ajustes > Activar modo desarrollador
2. Aplicaciones > Actualizar lista de aplicaciones
3. Buscar tu módulo e instalarlo/actualizarlo

### Modo Desarrollador con Recarga Automática

El contenedor está configurado con `--dev=reload,qweb,werkzeug,xml` que:
- **reload**: Recarga automática cuando cambias archivos Python
- **qweb**: Recarga plantillas QWeb
- **werkzeug**: Modo debug de Werkzeug
- **xml**: Valida archivos XML

## Comandos Útiles

```bash
# Entrar al contenedor de Odoo
docker exec -it odoo17-dev bash

# Ver logs de Odoo
docker-compose logs -f odoo

# Reiniciar solo Odoo
docker-compose restart odoo

# Recrear contenedores
docker-compose up -d --force-recreate

# Limpiar todo (¡borra datos!)
docker-compose down -v
```

## Scaffold - Crear módulo base

```bash
# Crear estructura de módulo
docker exec -it odoo17-dev odoo scaffold nombre_modulo /mnt/extra-addons
```

## Base de Datos

### Backup
```bash
docker exec odoo17-db pg_dump -U odoo nombre_db > backup.sql
```

### Restore
```bash
docker exec -i odoo17-db psql -U odoo nombre_db < backup.sql
```

## Solución de Problemas

### El módulo no aparece
1. Asegúrate de que el `__manifest__.py` esté correcto
2. Activa el modo desarrollador
3. Ve a Aplicaciones > Actualizar lista de aplicaciones
4. Busca el módulo por su nombre técnico

### Errores de permisos
```bash
# En Windows, los permisos suelen funcionar sin problemas
# Si hay problemas, reinicia Docker Desktop
```

### Limpiar y empezar de nuevo
```bash
docker-compose down -v
docker-compose up -d
```
