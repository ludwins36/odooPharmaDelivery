# -*- coding: utf-8 -*-

import json
import logging
from odoo import http
from odoo.http import request
from .main import VeloxBridgeController

_logger = logging.getLogger(__name__)


class CategoriesAPIController(VeloxBridgeController):
    """API para gestión de categorías de producto"""

    @http.route('/api/v1/categories', type='http', auth='none', methods=['POST'], csrf=False)
    def create_category(self):
        """
        Crear o actualizar categoría desde PrestaShop
        
        Body JSON esperado:
        {
            "name": "Electrónica",
            "parent_id": null,
            "description": "Productos electrónicos",
            "active": true
        }
        """
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        user = result
        
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return self._error_response(f"JSON inválido: {str(e)}")

        required_fields = ['name']
        for field in required_fields:
            if field not in data:
                return self._error_response(f"Campo requerido: {field}")

        try:
            category = self._process_category(user, data)
            self._log_operation(
                'import', 'product.category',
                record_id=category.id,
                status='success',
                message=f"Categoría procesada: {data.get('name')}",
                user=user
            )
            
            return self._success_response(
                data={
                    'odoo_id': category.id,
                    'name': category.name,
                    'complete_name': category.complete_name
                },
                message="Categoría procesada correctamente"
            )
            
        except Exception as e:
            _logger.exception("Error al procesar categoría")
            self._log_operation(
                'import', 'product.category',
                status='error',
                message=str(e),
                user=user
            )
            return self._error_response(f"Error al procesar categoría: {str(e)}", status=500)

    def _process_category(self, user, data):
        """Procesa y crea/actualiza la categoría"""
        Category = request.env['product.category'].sudo()
        
        # Buscar categoría existente por odoo_id
        existing = None
        if data.get('odoo_id'):
            existing = Category.browse(int(data.get('odoo_id')))
            if not existing.exists(): existing = None
        
        # Buscar categoría padre si existe (por odoo_id)
        parent_id = False
        if data.get('parent_id'):
            parent = Category.browse(int(data.get('parent_id')))
            if parent.exists():
                parent_id = parent.id
        
        vals = {
            'name': data.get('name'),
            'parent_id': parent_id,
        }

        if existing:
            existing.write(vals)
            return existing
        else:
            return Category.create(vals)

    @http.route('/api/v1/categories', type='http', auth='none', methods=['GET'], csrf=False)
    def get_categories(self):
        """Obtener lista de categorías"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result

        try:
            categories = request.env['product.category'].sudo().search([])
            
            data = [{
                'odoo_id': c.id,
                'name': c.name,
                'complete_name': c.complete_name,
                'parent_id': c.parent_id.id if c.parent_id else None
            } for c in categories]
            
            return self._success_response(data=data)
            
        except Exception as e:
            return self._error_response(str(e), status=500)

    @http.route('/api/v1/categories/<int:odoo_id>', type='http', auth='none', 
                methods=['GET'], csrf=False)
    def get_category(self, odoo_id):
        """Obtener categoría por ID Odoo"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result

        category = request.env['product.category'].sudo().browse(int(odoo_id))
        
        if not category.exists():
             return self._error_response("Categoría no encontrada", status=404)
        
        return self._success_response(data={
            'odoo_id': category.id,
            'name': category.name,
            'complete_name': category.complete_name,
            'parent_id': category.parent_id.id if category.parent_id else None
        })

    @http.route('/api/v1/categories/bulk', type='http', auth='none', 
                methods=['POST'], csrf=False)
    def bulk_create_categories(self):
        """
        Crear múltiples categorías en lote
        
        Body JSON esperado:
        {
            "categories": [
                {...categoria1...},
                {...categoria2...}
            ]
        }
        
        IMPORTANTE: Enviar categorías padre antes que las hijas
        """
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        user = result
        
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return self._error_response(f"JSON inválido: {str(e)}")

        categories = data.get('categories', [])
        if not categories:
            return self._error_response("No se proporcionaron categorías")

        results = []
        errors = []
        
        for cat_data in categories:
            try:
                category = self._process_category(user, cat_data)
                results.append({
                    'odoo_id': category.id,
                    'status': 'success'
                })
            except Exception as e:
                errors.append({
                    'name': cat_data.get('name'),
                    'error': str(e),
                    'status': 'error'
                })

        return self._success_response(
            data={
                'processed': len(results),
                'errors': len(errors),
                'results': results,
                'error_details': errors
            },
            message=f"Procesadas {len(results)} categorías, {len(errors)} errores"
        )
