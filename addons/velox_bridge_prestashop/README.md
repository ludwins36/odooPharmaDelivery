# Velox Bridge PrestaShop - API REST

## Descripción

Módulo de Odoo 17 que expone APIs REST para integración con PrestaShop. Permite que PrestaShop envíe datos a Odoo para sincronizar productos, clientes, atributos, categorías y crear cotizaciones desde órdenes.

## APIs Disponibles

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/health` | GET | Verificar estado de la API |
| `/api/v1/login` | POST | Iniciar sesión y obtener session_id |
| `/api/v1/is_logged` | POST | Verificar si la sesión está activa |
| `/api/v1/logout` | POST | Cerrar sesión |
| `/api/v1/test-auth` | GET | Probar autenticación |
| `/api/v1/products` | POST | Crear/actualizar producto |
| `/api/v1/products` | GET | Listar productos |
| `/api/v1/products/{id}` | GET | Obtener producto |
| `/api/v1/products/bulk` | POST | Crear múltiples productos |
| `/api/v1/customers` | POST | Crear/actualizar cliente |
| `/api/v1/customers` | GET | Listar clientes |
| `/api/v1/customers/{id}` | GET | Obtener cliente |
| `/api/v1/customers/bulk` | POST | Crear múltiples clientes |
| `/api/v1/attributes` | POST | Crear/actualizar atributo |
| `/api/v1/attributes` | GET | Listar atributos |
| `/api/v1/attributes/bulk` | POST | Crear múltiples atributos |
| `/api/v1/categories` | POST | Crear/actualizar categoría |
| `/api/v1/categories` | GET | Listar categorías |
| `/api/v1/categories/bulk` | POST | Crear múltiples categorías |
| `/api/v1/orders` | POST | Crear cotización |
| `/api/v1/orders` | GET | Listar órdenes |
| `/api/v1/orders/{id}` | GET | Obtener orden |
| `/api/v1/orders/{id}/confirm` | POST | Confirmar orden |
| `/api/v1/orders/{id}/cancel` | POST | Cancelar orden |

## Autenticación

Todos los endpoints (excepto `/api/v1/health`) requieren el header:

```
X-API-Key: tu-api-key
```

## Estructura del Módulo

```
velox_bridge_prestashop/
├── __manifest__.py
├── __init__.py
├── controllers/
│   ├── __init__.py
│   ├── main.py              # Controlador base
│   ├── api_products.py      # API de productos
│   ├── api_customers.py     # API de clientes
│   ├── api_attributes.py    # API de atributos
│   ├── api_categories.py    # API de categorías
│   └── api_orders.py        # API de órdenes
├── models/
│   ├── __init__.py
│   ├── prestashop_backend.py
│   ├── prestashop_log.py
│   ├── res_partner.py
│   ├── product_template.py
│   ├── product_category.py
│   ├── product_attribute.py
│   └── sale_order.py
├── views/
│   ├── prestashop_backend_views.xml
│   ├── prestashop_log_views.xml
│   ├── res_partner_views.xml
│   ├── product_views.xml
│   └── menu_views.xml
├── security/
│   ├── velox_bridge_security.xml
│   └── ir.model.access.csv
└── static/description/
    ├── icon.png
    └── index.html
```

## Ejemplos de Uso

### Crear producto

```bash
curl -X POST http://localhost:8069/api/v1/products \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-api-key" \
  -d '{
    "prestashop_id": 123,
    "reference": "PROD-001",
    "name": "Mi Producto",
    "price": 99.99,
    "cost": 50.00,
    "category_id": 1
  }'
```

### Crear cliente

```bash
curl -X POST http://localhost:8069/api/v1/customers \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-api-key" \
  -d '{
    "prestashop_id": 456,
    "email": "cliente@email.com",
    "firstname": "Juan",
    "lastname": "Pérez",
    "addresses": [
      {
        "prestashop_id": 1,
        "type": "invoice",
        "street": "Calle Principal 1",
        "city": "Madrid",
        "zip": "28001",
        "country_code": "ES"
      }
    ]
  }'
```

### Crear orden/cotización

```bash
curl -X POST http://localhost:8069/api/v1/orders \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-api-key" \
  -d '{
    "prestashop_id": 789,
    "reference": "PS-ORDER-789",
    "customer_prestashop_id": 456,
    "shipping_cost": 5.99,
    "lines": [
      {
        "prestashop_product_id": 123,
        "product_name": "Mi Producto",
        "quantity": 2,
        "unit_price": 99.99
      }
    ]
  }'
```

### Crear categoría

```bash
curl -X POST http://localhost:8069/api/v1/categories \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-api-key" \
  -d '{
    "prestashop_id": 10,
    "name": "Electrónica",
    "parent_id": null
  }'
```

### Crear atributo con valores

```bash
curl -X POST http://localhost:8069/api/v1/attributes \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-api-key" \
  -d '{
    "prestashop_id": 1,
    "name": "Color",
    "type": "radio",
    "values": [
      {"prestashop_id": 1, "name": "Rojo"},
      {"prestashop_id": 2, "name": "Azul"}
    ]
  }'
```

## Configuración

1. Instalar el módulo en Odoo
2. Ir a **Velox Bridge > Configuración > Backends**
3. Crear un nuevo backend con nombre descriptivo
4. Copiar la **API Key** generada automáticamente
5. Usar la API Key en las llamadas desde PrestaShop

## Licencia

LGPL-3
