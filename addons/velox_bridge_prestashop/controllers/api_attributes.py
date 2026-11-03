# -*- coding: utf-8 -*-

import json
import logging
from odoo import http
from odoo.http import request
from .main import VeloxBridgeController

_logger = logging.getLogger(__name__)


class AttributesAPIController(VeloxBridgeController):
    """API para gestión de atributos de producto"""

    @http.route('/api/v1/attributes', type='http', auth='none', methods=['POST'], csrf=False)
    def create_attribute(self):
        """
        Crear o actualizar atributo (usar `odoo_id` opcional para actualizar)

        Body JSON ejemplo:
        {
            "odoo_id": 5,    # opcional
            "name": "Color",
            "type": "radio",
            "values": [ {"name": "Rojo"}, {"name": "Azul"} ]
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
            attribute = self._process_attribute(user, data)
            self._log_operation(
                'import', 'product.attribute',
                record_id=attribute.id,
                status='success',
                message=f"Atributo procesado: {data.get('name')}",
                user=user
            )

            # Obtener valores creados
            values_data = [{
                'odoo_id': v.id,
                'name': v.name
            } for v in attribute.value_ids]

            return self._success_response(
                data={
                    'odoo_id': attribute.id,
                    'name': attribute.name,
                    'values': values_data
                },
                message="Atributo procesado correctamente"
            )
            
        except Exception as e:
            _logger.exception("Error al procesar atributo")
            self._log_operation(
                'import', 'product.attribute',
                status='error',
                message=str(e),
                user=user
            )
            return self._error_response(f"Error al procesar atributo: {str(e)}", status=500)

    def _process_attribute(self, user, data):
        """Procesa y crea/actualiza el atributo"""
        Attribute = request.env['product.attribute'].sudo()
        AttributeValue = request.env['product.attribute.value'].sudo()
        
        type_mapping = {
            'select': 'radio',
            'radio': 'radio',
            'color': 'color',
        }
        
        # Buscar por odoo_id si viene, sino por nombre
        existing = None
        if data.get('odoo_id'):
            try:
                existing = Attribute.sudo().browse(int(data.get('odoo_id')))
                if not existing.exists():
                    existing = None
            except Exception:
                existing = None
        if not existing:
            existing = Attribute.search([
                ('name', '=', data.get('name'))
            ], limit=1)
        
        vals = {
            'name': data.get('name'),
            'display_type': type_mapping.get(data.get('type'), 'radio'),
            'create_variant': 'always',
        }

        if existing:
            existing.write(vals)
            attribute = existing
        else:
            attribute = Attribute.create(vals)

        # Procesar valores del atributo
        if data.get('values'):
            for val_data in data.get('values'):
                existing_val = AttributeValue.search([
                    ('name', '=', val_data.get('name')),
                    ('attribute_id', '=', attribute.id)
                ], limit=1)

                val_vals = {
                    'name': val_data.get('name'),
                    'attribute_id': attribute.id,
                }

                if existing_val:
                    existing_val.write(val_vals)
                else:
                    AttributeValue.create(val_vals)

        return attribute

    @http.route('/api/v1/attributes', type='http', auth='none', methods=['GET'], csrf=False)
    def get_attributes(self):
        """Obtener lista de atributos sincronizados"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result

        try:
            attributes = request.env['product.attribute'].sudo().search([])

            data = [{
                'odoo_id': a.id,
                'name': a.name,
                'type': a.display_type,
                'values': [{
                    'odoo_id': v.id,
                    'name': v.name
                } for v in a.value_ids]
            } for a in attributes]
            
            return self._success_response(data=data)
            
        except Exception as e:
            return self._error_response(str(e), status=500)

    @http.route('/api/v1/attributes/<int:odoo_id>', type='http', auth='none', 
                methods=['GET'], csrf=False)
    def get_attribute(self, odoo_id):
        """Obtener atributo por id de Odoo"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        user = result

        attribute = request.env['product.attribute'].sudo().browse(int(odoo_id))
        if not attribute.exists():
            return self._error_response("Atributo no encontrado", status=404)

        return self._success_response(data={
            'odoo_id': attribute.id,
            'name': attribute.name,
            'type': attribute.display_type,
            'values': [{
                'odoo_id': v.id,
                'name': v.name
            } for v in attribute.value_ids]
        })

    @http.route('/api/v1/attributes/bulk', type='http', auth='none', 
                methods=['POST'], csrf=False)
    def bulk_create_attributes(self):
        """
        Crear múltiples atributos en lote
        
        Body JSON esperado:
        {
            "attributes": [
                {...atributo1...},
                {...atributo2...}
            ]
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

        attributes = data.get('attributes', [])
        if not attributes:
            return self._error_response("No se proporcionaron atributos")

        results = []
        errors = []
        
        for attr_data in attributes:
            try:
                attribute = self._process_attribute(user, attr_data)
                results.append({
                    'odoo_id': attribute.id,
                    'status': 'success'
                })
            except Exception as e:
                errors.append({
                    'odoo_id': attr_data.get('odoo_id'),
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
            message=f"Procesados {len(results)} atributos, {len(errors)} errores"
        )
