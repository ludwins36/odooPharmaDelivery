# -*- coding: utf-8 -*-

import json
import logging
from odoo import http, fields, api
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

FORCE_DISABLE_API = False


class VeloxBridgeController(http.Controller):
    """Controlador principal para validación de API"""

    def _is_api_disabled(self):
        if FORCE_DISABLE_API: 
            return True

        # try:
        #     raw_value = request.env['ir.config_parameter'].sudo().get_param(
        #         'velox_bridge_prestashop.api_disabled',
        #         default='0'
        #     )
        #     return str(raw_value).strip().lower() in ('1', 'true', 'yes', 'on')
        # except Exception as e:
        #     _logger.error("No se pudo leer velox_bridge_prestashop.api_disabled: %s", str(e))
        #     return False

    def _validate_api_key(self):
        """Valida la API key del header"""
        if self._is_api_disabled():
            return False, {
                'status': 503,
                'code': 503,
                'message': "API temporalmente deshabilitada por mantenimiento"
            }

        api_key = request.httprequest.headers.get('X-API-Key')
        if not api_key:
            return False, "API Key no proporcionada"

        # Validamos que exista el modelo de API Keys (nativo de Odoo)
        if 'res.users.apikeys' not in request.env:
            return False, "El sistema de API Keys no está disponible"

        ApiKeyModel = request.env['res.users.apikeys'].sudo()
        
        # Validamos que exista el método _check_credentials
        if not hasattr(ApiKeyModel, '_check_credentials'):
            return False, "El método de validación de credenciales no está disponible"

        try:
            # En Odoo 17, se usa key=api_key
            uid = ApiKeyModel._check_credentials(key=api_key, scope='rpc')

            if not uid:
                return False, "API Key inválida"
            
            user = request.env['res.users'].sudo().browse(uid)
            if user.active:
                # Fijar el usuario autenticado en el request/env actual.
                # Esto permite que request.env use ese usuario durante el ciclo HTTP.
                request.update_env(user=uid)
                request.update_context(
                    api_user_id=uid,
                    lang=user.lang or request.env.lang,
                    tz=user.tz or request.env.context.get('tz')
                )
                return True, user
            else:
                return False, "Usuario inactivo"

        except Exception as e:
            _logger.error("Excepción validando API Key: %s", str(e))
            return False, f"Error interno al validar credenciales API Key: {str(e)}" 

    def _json_response(self, data, status=200):
        """Genera respuesta JSON estandarizada"""
        return Response(
            json.dumps(data, default=str),
            status=status,
            mimetype='application/json'
        )

    def _error_response(self, message, status=400, code=None):
        """Genera respuesta de error"""
        # Permite sobreescribir status/message desde un payload interno (ej. _validate_api_key)
        if isinstance(message, dict):
            status = int(message.get('status', status))
            code = message.get('code', code or status)
            message = message.get('message', 'Error')

        return self._json_response({
            'success': False,
            'error': {
                'code': code or status,
                'message': message
            }
        }, status=status)

    def _success_response(self, data=None, message="Operación exitosa"):
        """Genera respuesta exitosa"""
        response = {
            'success': True,
            'message': message
        }
        if data is not None:
            response['data'] = data
        return self._json_response(response, status=200)

    def _log_operation(self, operation, model, record_id=None, 
                       status='success', message=None, user=None):
        """Registra operación en el log"""

        try:
            user_id = user.id if user else request.env.user.id
            
            # Usar un cursor nuevo para asegurar que el log se guarde incluso si la transacción principal falla
            with request.registry.cursor() as new_cr:
                env = api.Environment(new_cr, request.uid, request.context)
                env['prestashop.log'].sudo().create({
                    'user_id': user_id,
                    'operation': operation,
                    'model': model,
                    'record_id': record_id,
                    'status': status,
                    'message': message,
                })
                new_cr.commit()
                
        except Exception as e:
            # Fallback a logger estándar si falla la escritura en BD 
            _logger.error(f"No se pudo guardar log en DB: {str(e)} - Mensaje original: {message}")

    @http.route('/api/v1/health', type='http', auth='none', methods=['GET'], csrf=False)
    def health_check(self):
        """Endpoint para verificar estado de la API"""
        return self._success_response(
            data={'status': 'healthy', 'version': '1.0.0'},
            message="API funcionando correctamente"
        )

    @http.route('/api/v1/test-auth', type='http', auth='none', methods=['GET'], csrf=False)
    def test_auth(self):
        """Endpoint para probar autenticación"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        return self._success_response(
            data={'user': result.name, 'user_id': result.id},
            message="Autenticación exitosa"
        )

    @http.route('/api/v1/auth/validate', type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    def validate_api_key_endpoint(self):
        """Endpoint específico para validar API Key"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        return self._success_response(
            data={'valid': True, 'user_id': result.id, 'user_name': result.name},
            message="API Key válida"
        )

    @http.route('/api/v1/endpoints', type='http', auth='none', methods=['GET'], csrf=False)
    def list_endpoints(self):
        """Lista los endpoints disponibles (Público, sin auth)"""
        endpoints = [
            {'method': 'GET', 'path': '/api/v1/health', 'description': 'Verificar estado del servicio'},
            {'method': 'GET', 'path': '/api/v1/endpoints', 'description': 'Listar métodos disponibles'},
            {'method': 'GET/POST', 'path': '/api/v1/auth/validate', 'description': 'Validar API Key'},
            {'method': 'GET', 'path': '/api/v1/products', 'description': 'Listar productos'},
            {'method': 'POST', 'path': '/api/v1/products', 'description': 'Crear/Actualizar productos'},
            {'method': 'GET', 'path': '/api/v1/products/<id>', 'description': 'Obtener producto'},
            {'method': 'GET', 'path': '/api/v1/customers', 'description': 'Listar clientes'},
            {'method': 'POST', 'path': '/api/v1/customers', 'description': 'Crear/Actualizar clientes'},
            {'method': 'GET', 'path': '/api/v1/customers/<id>', 'description': 'Obtener cliente'},
            {'method': 'GET', 'path': '/api/v1/orders', 'description': 'Listar pedidos'},
            {'method': 'POST', 'path': '/api/v1/orders', 'description': 'Crear pedido'},
            {'method': 'GET', 'path': '/api/v1/categories', 'description': 'Listar categorías'},
            {'method': 'GET', 'path': '/api/v1/attributes', 'description': 'Listar atributos'},
            {'method': 'GET', 'path': '/api/v1/discounts', 'description': 'Listar descuentos (Listas de precios)'},
            {'method': 'GET', 'path': '/api/v1/discounts/<id>', 'description': 'Obtener descuento por ID'},
        ]
        
        return self._success_response(
            data={'endpoints': endpoints},
            message="Endpoints disponibles"
        )
