# -*- coding: utf-8 -*-
{
    'name': 'Velox Bridge PrestaShop',
    'version': '17.0.1.0.3',
    'summary': 'API REST para integración con PrestaShop',
    'description': """
        Módulo que expone APIs REST para integración con PrestaShop.
        
        APIs disponibles:
        - /api/v1/products - Importar productos
        - /api/v1/customers - Importar clientes
        - /api/v1/attributes - Importar atributos
        - /api/v1/categories - Importar categorías
        - /api/v1/orders - Crear cotizaciones desde órdenes
    """,
    'author': 'Velox',
    'website': 'https://www.velox.com',
    'category': 'Sales/Sales',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'contacts',
        'product',
        'sale_management',
    ],
    'data': [
        'security/velox_bridge_security.xml',
        'security/ir.model.access.csv',
        'views/prestashop_log_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
