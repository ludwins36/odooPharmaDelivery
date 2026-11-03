# -*- coding: utf-8 -*-

import json
import logging
from odoo import http
from odoo.http import request
from .main import VeloxBridgeController

_logger = logging.getLogger(__name__)


class CustomersAPIController(VeloxBridgeController):
    """API para gestión de clientes"""

    @http.route('/api/v1/customers', type='http', auth='none', methods=['POST'], csrf=False)
    def create_customer(self):
        """
        Crear o actualizar cliente desde PrestaShop
        
        Body JSON ejemplo:
        {
            "odoo_id": 45,            # opcional, si se envía actualiza
            "email": "cliente@email.com",
            "firstname": "Juan",
            "lastname": "Pérez",
            "company": "Mi Empresa",
            "vat": "B12345678",
            "phone": "+34600000000",
            "mobile": "+34600000001",
            "addresses": [
                {
                    "type": "invoice",
                    "street": "Calle Principal 1",
                    "street2": "Piso 2",
                    "city": "Madrid",
                    "zip": "28001",
                    "country_code": "ES",
                    "state_code": "M"
                }
            ]
        }
        """
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        # result is the res.users record (usuario que tiene la API Key)
        user = result
        
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return self._error_response(f"JSON inválido: {str(e)}")

        required_fields = ['email']
        for field in required_fields:
            if field not in data:
                return self._error_response(f"Campo requerido: {field}")

        try:
            partner = self._process_customer(user, data)
            self._log_operation(
                'import', 'res.partner',
                record_id=partner.id,
                status='success',
                message=f"Cliente procesado: {partner.name}",
                user=user
            )
            
            return self._success_response(
                data={
                    'odoo_id': partner.id,
                    'name': partner.name,
                    'email': partner.email
                },
                message="Cliente procesado correctamente"
            )
            
        except Exception as e:
            _logger.exception("Error al procesar cliente")
            self._log_operation(
                'import', 'res.partner',
                status='error',
                message=str(e),
                user=user
            )
            return self._error_response(f"Error al procesar cliente: {str(e)}", status=500)

    def _process_customer(self, user, data):
        """Procesa y crea/actualiza el cliente"""
        Partner = request.env['res.partner'].sudo()
        
        # Buscar cliente existente por `odoo_id` si se proporcionó, sino por email
        existing = None
        if data.get('odoo_id'):
            try:
                existing = Partner.sudo().browse(int(data.get('odoo_id')))
                if not existing.exists():
                    existing = None
            except Exception:
                existing = None
        if not existing:
            existing = Partner.search([
                ('email', '=', data.get('email')), ('parent_id', '=', False)
            ], limit=1)
        
        # Construir nombre
        name_parts = []
        if data.get('firstname'):
            name_parts.append(data.get('firstname'))
        if data.get('lastname'):
            name_parts.append(data.get('lastname'))
        name = ' '.join(name_parts) if name_parts else data.get('email')
        
        # Determinar si es empresa
        is_company = bool(data.get('company'))
        
        vals = {
            'name': data.get('company') if is_company else name,
            'email': data.get('email'),
            'phone': data.get('phone'),
            'mobile': data.get('mobile'),
            'vat': data.get('vat'),
            'is_company': is_company,
            'customer_rank': 1,
        }

        if existing:
            existing.write(vals)
            partner = existing
        else:
            partner = Partner.create(vals)

        # Procesar direcciones
        if data.get('addresses'):
            self._process_addresses(partner, data.get('addresses'))

        return partner

    def _process_addresses(self, parent_partner, addresses):
        """Procesa las direcciones del cliente"""
        Partner = request.env['res.partner'].sudo()
        Country = request.env['res.country'].sudo()
        State = request.env['res.country.state'].sudo()
        
        for addr_data in addresses:
            # Buscar país
            country = Country.search([
                ('code', '=', addr_data.get('country_code', 'ES'))
            ], limit=1)
            
            # Buscar estado/provincia
            state = False
            if addr_data.get('state_code') and country:
                state = State.search([
                    ('code', '=', addr_data.get('state_code')),
                    ('country_id', '=', country.id)
                ], limit=1)
            
            # Buscar dirección existente: preferir `odoo_address_id` si viene, sino buscar por parent+street+zip
            existing_addr = None
            if addr_data.get('odoo_address_id'):
                try:
                    existing_addr = Partner.sudo().browse(int(addr_data.get('odoo_address_id')))
                    if not existing_addr.exists() or existing_addr.parent_id.id != parent_partner.id:
                        existing_addr = None
                except Exception:
                    existing_addr = None
            if not existing_addr:
                # fallback por campos de dirección
                search_domain = [('parent_id', '=', parent_partner.id)]
                if addr_data.get('street'):
                    search_domain.append(('street', '=', addr_data.get('street')))
                if addr_data.get('zip'):
                    search_domain.append(('zip', '=', addr_data.get('zip')))
                existing_addr = Partner.search(search_domain, limit=1)
            
            addr_type = addr_data.get('type', 'contact')
            type_mapping = {
                'invoice': 'invoice',
                'delivery': 'delivery',
                'shipping': 'delivery',
                'other': 'other'
            }
            
            addr_vals = {
                'parent_id': parent_partner.id,
                'type': type_mapping.get(addr_type, 'contact'),
                'name': parent_partner.name,
                'street': addr_data.get('street'),
                'street2': addr_data.get('street2'),
                'city': addr_data.get('city'),
                'zip': addr_data.get('zip'),
                'country_id': country.id if country else False,
                'state_id': state.id if state else False,
                # no se almacena prestashop_address_id; usar odoo_address_id si se necesita
            }
            
            if existing_addr:
                existing_addr.write(addr_vals)
            else:
                Partner.create(addr_vals)

    @http.route('/api/v1/customers', type='http', auth='none', methods=['GET'], csrf=False)
    def get_customers(self):
        """Obtener lista de clientes sincronizados"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result
        
        try:
            partners = request.env['res.partner'].sudo().search([
                ('customer_rank', '>', 0),
                ('parent_id', '=', False)
            ])

            data = [{
                'odoo_id': p.id,
                'name': p.name,
                'email': p.email,
                'vat_type': p.l10n_latam_identification_type_id.id if p.l10n_latam_identification_type_id else False,
                'is_company': p.is_company,
                'address': p.street,
                'address2': p.street2,
                'city': p.city,
                'zip': p.zip,
                'country': p.country_id.code if p.country_id else False,
                'state': p.state_id.name if p.state_id else False,
                'phone': p.phone,
                'mobile': p.mobile,
                'vat': p.vat,
            } for p in partners]
            
            return self._success_response(data=data)
            
        except Exception as e:
            return self._error_response(str(e), status=500)

    @http.route('/api/v1/customers/<int:odoo_id>', type='http', auth='none', methods=['GET'], csrf=False)
    def get_customer(self, odoo_id):
        """Obtener cliente por id de Odoo"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        user = result

        partner = request.env['res.partner'].sudo().browse(int(odoo_id))
        if not partner.exists() or partner.parent_id:
            return self._error_response("Cliente no encontrado", status=404)
        
        if not partner:
            return self._error_response("Cliente no encontrado", status=404)
        
        # Obtener direcciones
        addresses = []
        for child in partner.child_ids:
            addresses.append({
                'odoo_address_id': child.id,
                'type': child.type,
                'street': child.street,
                'city': child.city,
                'zip': child.zip
            })
        
        return self._success_response(data={
            'odoo_id': partner.id,
            'name': partner.name,
            'email': partner.email,
            'phone': partner.phone,
            'mobile': partner.mobile,
            'is_company': partner.is_company,
            'addresses': addresses
        })

    @http.route('/api/v1/customers/bulk', type='http', auth='none', 
                methods=['POST'], csrf=False)
    def bulk_create_customers(self):
        """
        Crear múltiples clientes en lote
        
        Body JSON esperado:
        {
            "customers": [
                {...cliente1...},
                {...cliente2...}
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

        customers = data.get('customers', [])
        if not customers:
            return self._error_response("No se proporcionaron clientes")

        results = []
        errors = []
        
        for customer_data in customers:
            try:
                partner = self._process_customer(user, customer_data)
                results.append({
                    'odoo_id': partner.id,
                    'status': 'success'
                })
            except Exception as e:
                errors.append({
                    'odoo_id': customer_data.get('odoo_id'),
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
            message=f"Procesados {len(results)} clientes, {len(errors)} errores"
        )
