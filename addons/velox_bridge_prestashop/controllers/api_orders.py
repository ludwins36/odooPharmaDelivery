# -*- coding: utf-8 -*-

import json
import logging
import traceback
from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from .main import VeloxBridgeController
import base64

_logger = logging.getLogger(__name__)


class OrdersAPIController(VeloxBridgeController):
    """API para gestión de órdenes/cotizaciones"""

    @http.route('/api/v1/orders/simulate', type='http', auth='none', methods=['POST'], csrf=False)
    def simulate_order(self):
        """
        Simula una orden para calcular totales usando SaleOrder.new()
        """
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
        except Exception as e:
            return self._error_response(f"JSON inválido: {str(e)}")

        try:
            order = self._process_simulate_order(user, data)

            total_discount = sum([
                (line.price_unit * line.product_uom_qty * (line.discount / 100.0)) if line.discount else 0.0
                for line in order.order_line
            ])
            
            response_data = {
                'amount_untaxed': order.amount_untaxed,
                'amount_tax': order.amount_tax,
                'amount_total': order.amount_total,
                'discount_total': total_discount,
                'payment_method': order.l10n_latam_payment_method_id.name if hasattr(order, 'l10n_latam_payment_method_id') else None,
                'order_type': order.l10n_latam_order_type_id.name if hasattr(order, 'l10n_latam_order_type_id') else None,
                'json_fmp': order.health_fmp_json,  
                'shipping_cost': 0.0,
                'lines': []
            }
            
            # Iterar sobre las líneas virtuales
            for line in order.order_line:
                discount_amount = (line.price_unit * line.product_uom_qty * (line.discount / 100.0)) if line.discount else 0.0
                line_data = {
                    'product_id': line.product_id.id,
                    'name': line.name,
                    'quantity': line.product_uom_qty,
                    'price_unit': line.price_unit,
                    'discount': line.discount,
                    'reference': line.product_id.default_code,
                    'discount_amount': discount_amount,
                    'price_subtotal': line.price_subtotal,
                    'price_total': line.price_total,
                    'price_tax': line.price_tax,
                }
                # Identificar envío por código si es posible, o por producto si lo seteamos
                if line.product_id.default_code == 'SHIP-PS':
                    response_data['shipping_cost'] = line.price_total
                else:
                    response_data['lines'].append(line_data)

            return self._success_response(
                data=response_data,
                message="Simulación calculada correctamente (Virtual)"
            )

        except Exception as e:
            _logger.exception("Error en simulacion virtual")
            return self._error_response(f"Error en simulacion: {str(e)}", status=500)

    def _process_simulate_order(self, user, data):
        """Procesa y crea una cotización VIRTUAL en memoria (SaleOrder.new)"""
        SaleOrder = request.env['sale.order'].sudo()
        Partner = request.env['res.partner'].sudo()

        Product = request.env['product.product'].sudo()
        
        vat = data.get('customer_vat')
        email = data.get('customer_email')
        partner = None

        if vat:
            partner = Partner.search([('vat', '=', vat)], limit=1)
        if not partner and email:
            partner = Partner.search([('email', '=', email)], limit=1)
        
        if not partner:
             # Fallback: Usar Public User o el primer cliente disponible
             # Esto es necesario porque new() necesita un partner_id real para calcular impuestos
            partner = request.env.ref('base.public_partner', raise_if_not_found=False) or Partner.search([], limit=1)

        currency = request.env['res.currency'].sudo().search([
            ('name', '=', data.get('currency_code', 'USD'))
        ], limit=1)

        payment = data.get('payment_method_id')
        order_type = data.get('order_type')

        order_vals = {
            'partner_id': partner.id,
            'l10n_latam_payment_method_id': payment if payment else None,
            'l10n_latam_order_type_id': order_type if order_type else None,
            'company_id': user.company_id.id or request.env.company.id,
            'date_order': data.get('date_add'),
        }

        if currency:
            order_vals['currency_id'] = currency.id

        order = SaleOrder.new(order_vals)
        if hasattr(order, '_onchange_partner_id'):
            order._onchange_partner_id()

        valid_lines = []
        products = data.get('products')

        for line_data in products:
            product = None
            if line_data.get('product_id'):
                product = Product.browse(int(line_data.get('product_id')))

            if not product and line_data.get('product_reference'):
                product = Product.search([('default_code', '=', line_data.get('product_reference'))], limit=1)
            
            if not product:
                continue

            line_vals = {
                'order_id': order.id,
                'product_id': product.id,
                'product_uom_qty': line_data.get('quantity', 1),
            }
            
            line = order.order_line.new(line_vals)
            line._compute_amount()
            
            valid_lines.append(line)

        # 6. Método de Envío (Virtual)
        shipping_method_name = data.get('shipping_method')
        shipping_cost = float(data.get('shipping_cost', 0.0))
        
        if shipping_method_name and shipping_cost > 0:
            carrier_product = Product.search([('name', '=', shipping_method_name), ('type', '=','service')], limit=1)

            if not carrier_product:
                carrier_product = Product.search([('default_code', '=', 'SHIP-PS')], limit=1)
            
            if carrier_product:
                ship_line = order.order_line.new({
                    'order_id': order.id,
                    'product_id': carrier_product.id,
                    'product_uom_qty': 1,
                    'price_unit': shipping_cost,
                    'name': shipping_method_name
                })
                ship_line.price_unit = shipping_cost
                ship_line._compute_amount()
                valid_lines.append(ship_line)

        if valid_lines:
            lines_recordset = valid_lines[0]
            for l in valid_lines[1:]:
                lines_recordset += l
            order.order_line = lines_recordset

        order._compute_amounts() 
        order._compute_tax_totals() 
        
        return order

    @http.route('/api/v1/orders', type='http', auth='none', methods=['POST'], csrf=False)
    def create_order(self):
       
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        user = result
        
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return self._error_response(f"JSON inválido: {str(e)}")

        # Validaciones básicas
        if not data.get('products'):
             return self._error_response("La orden debe tener al menos una línea (products)")

       
        payment = data.get('payment_method_id')

        try:

            order = self._process_order(user, data)
            env = request.env(user=user.id)
            latam_sale_invoice = None  # l10n_latam.sale.invoice si aplica (p. ej. payment == 3)
            # Confirmar la orden (cotización → venta) solo si no tiene prescripción
            prescription_base64 = data.get('prescription_base64')
            confirm_error = None
            if not prescription_base64:
                try:
                    if hasattr(order, 'button_l10n_latam_preconfirm'):
                        _logger.info("Ejecutando validación fiscal Latam para %s", order.name)

                    if payment == 3:
                        order.button_l10n_latam_preconfirm()
                        voucher_ref = data.get('voucher_ref')
                        voucher_lot = data.get('lot')
                        voucher_TPV = 8
                        wizard = order.action_confirm()
                        res_id = wizard.get('res_id')
                        invoice = env['l10n_latam.sale.invoice'].browse(res_id)
                        invoice.write({
                            'journal_id': 59,
                            'payment_ids': [
                                (0, 0, {
                                    'journal_id': 26,
                                    'payment_method_line_id': 37,
                                    'l10n_latam_creditcard_voucher_ref': voucher_ref,
                                    'l10n_latam_creditcard_voucher_lot': voucher_lot,
                                    'l10n_latam_creditcard_pos_id': voucher_TPV,
                                    'currency_id': order.currency_id.id,
                                    'amount': order.amount_total,
                                    'reference': data.get('reference') if data else order.name,
                                })
                            ]
                        })

                        invoice.button_confirm()
                        latam_sale_invoice = invoice
                        order.invalidate_recordset()
                except (UserError, ValidationError) as e:
                    confirm_error = f"Error al confirmar automáticamente: {str(e)}"
                    _logger.warning("No se pudo confirmar la orden %s: %s", order.name, confirm_error)
                except Exception as e:
                    confirm_error = f"Error al confirmar automáticamente: {str(e)}"
                    _logger.exception("Error al confirmar la orden %s", order.name)

            # Si viene un link de prescripción en el request, agregarlo como nota
            # prescription_link = data.get('prescription_link')
            # if prescription_link:
            #     note_msg = f"Link de prescripción: <a href=\"{prescription_link}\" target=\"_blank\">Ver documento</a>"
            #     # order.note = (order.note or '') + ('\n' if order.note else '') + note_msg
            #     order.sudo().message_post(body=note_msg, subtype_xmlid="mail.mt_note")

            doctor_name = (data.get('doctor_name') or '').strip()
            if doctor_name:
                try:
                    order.sudo().message_post(
                        body=f"Médico prescriptor: {doctor_name}",
                        subtype_xmlid="mail.mt_note"
                    )
                except Exception as e:
                    _logger.error(f"Error al registrar doctor_name en la orden: {str(e)}")

            prescription_name = data.get('prescription_name', 'prescripcion.pdf')

            if prescription_base64:
                try:
                    # 1. Crear el adjunto en Odoo
                    attachment = request.env['ir.attachment'].sudo().create({
                        'name': prescription_name,
                        'type': 'binary',
                        'datas': prescription_base64, # Odoo decodifica el base64 automáticamente aquí
                        'res_model': 'sale.order',
                        'res_id': order.id,
                    })
            
                    # 2. Postear el mensaje adjuntando el archivo creado
                    order.sudo().message_post(
                        body="Se ha adjuntado la receta médica enviada desde PrestaShop.",
                        attachment_ids=[attachment.id],
                        subtype_xmlid="mail.mt_note"
                    )
                except Exception as e:
                    _logger.error(f"Error al adjuntar archivo: {str(e)}")

            self._log_operation(
                'import', 'sale.order',
                record_id=order.id,
                status='success',
                message=f"Cotización creada: {order.name}",
                user=user
            )
            response_data = {
                'odoo_id': order.id,
                'odoo_name': order.name,
                'state': order.state,
                'amount_total': order.amount_total,
            }
            response_data.update(
                self._collect_invoice_response_for_order(order, latam_sale_invoice)
            )

            response_data['confirm_error'] = confirm_error
            if confirm_error:
                response_data['confirmed'] = False
            else:
                response_data['confirmed'] = order.state == 'sale'

            return self._success_response(
                data=response_data,
                message="Cotización creada correctamente" + (" (no confirmada: " + confirm_error + ")" if confirm_error else "")
            )
        except Exception as e:
            _logger.exception("Error al procesar orden")
            status_code = 400 if isinstance(e, (UserError, ValidationError)) else 500
            detailed_error = f"{e.__class__.__name__}: {str(e)}"
            tb_last_line = traceback.format_exc().strip().splitlines()[-1]
            self._log_operation(
                'import', 'sale.order',
                status='error',
                message=detailed_error,
                user=user
            )
            return self._json_response({
                'success': False,
                'error': {
                    'code': status_code,
                    'message': "Error al procesar orden",
                    'error_type': e.__class__.__name__,
                    'error_message': str(e),
                    'trace': tb_last_line,
                }
            }, status=status_code)

    def _collect_invoice_response_for_order(self, order, latam_sale_invoice=None):
        """
        Datos de factura para la API: número(s) y ids de account.move si existen.
        Prioriza sale.order.invoice_ids; si no hay, intenta el move asociado al
        documento l10n_latam.sale.invoice (campos típicos move_id / account_move_id).
        """
        order = order.sudo()
        order.invalidate_recordset()
        out = {
            'invoice_name': None,
            'invoice_names': [],
            'account_move_ids': [],
        }
        moves = order.invoice_ids.filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund')
        )
        if moves:
            names = [n for n in moves.mapped('name') if n]
            out['invoice_names'] = names
            out['account_move_ids'] = moves.ids
            out['invoice_name'] = names[0] if names else (moves[0].name or None)
            return out

        if latam_sale_invoice and latam_sale_invoice.exists():
            move = getattr(latam_sale_invoice, 'move_id', False)
            if not move or not move.exists():
                move = getattr(latam_sale_invoice, 'account_move_id', False)
            if move and move.exists():
                name = move.name or None
                out['invoice_name'] = name
                out['invoice_names'] = [name] if name else []
                out['account_move_ids'] = [move.id]
        return out

    def _process_order(self, user, data):
        """Procesa y crea la cotización con el usuario autenticado por API key."""
        env = request.env(user=user.id)
        SaleOrder = env['sale.order']
        Partner = env['res.partner']
        
        # 1. Buscar Cliente (Partner) por VAT o Email
        vat = data.get('customer_vat')
        email = data.get('customer_email')
        partner = None

        if vat:
            partner = Partner.search([('vat', '=', vat)], limit=1)
        
        if not partner and email:
             partner = Partner.search([('email', '=', email)], limit=1)
            
        id_type = 4 if data.get('customer_vat_type') == 'ruc' else 5;

        if not partner:
            # Crear cliente si no existe
            # Usamos datos de factura para el nombre principal si están disponibles
            invoice_addr = data.get('address_invoice', {})
            
            partner = Partner.create({
                'name':  data.get('customer_fullname'),
                'email': email,
                'phone': invoice_addr.get('phone'),
                'vat': vat,
                'l10n_latam_identification_type_id': id_type,
                'customer_rank': 1,
                'company_type': 'company' if invoice_addr.get('company') else 'person',
            })
        
        # 2. Gestionar Direcciones (Shipping / Invoice)
        partner_invoice_id = self._find_or_create_address(
            user, partner, data.get('address_invoice'), 'invoice', id_type
        )
        partner_shipping_id = self._find_or_create_address(
            user, partner, data.get('address_shipping'), 'delivery', id_type
        )

        # 3. Datos generales de la orden
        currency = env['res.currency'].search([
            ('name', '=', data.get('currency_code', 'USD'))
        ], limit=1)

        order_type = data.get('order_type')
        payment = data.get('payment_method_id')
        doctor_id = data.get('doctor_id') or None


        order_vals = {
            'partner_id': partner.id,
            'partner_invoice_id': partner_invoice_id.id,
            'warehouse_id': 2,
            'health_doctor_id': doctor_id,
            # 'journal_id': 60,
            'l10n_latam_order_type_id': order_type if order_type else None,
            'partner_shipping_id': partner_shipping_id.id,
            'client_order_ref': data.get('reference_order'),  # Referencia legible
            'origin': f"PS-{data.get('id_order')}",     # ID interno PS en origen
            'date_order': data.get('date_add'),
            'l10n_latam_payment_method_id': payment if payment else None,
            'company_id': user.company_id.id or env.company.id,
            'user_id': user.id,  # Vendedor = usuario autenticado por API key
        }
        
        if currency:
            order_vals['currency_id'] = currency.id
        
        # Crear la orden
        order = SaleOrder.create(order_vals)
        
        # 4. Crear líneas de productos
        # Nota: El JSON entrante usa 'products' pero la funcion antigua esperaba 'lines'
        # o se debe adaptar el map o la llamada
        products = data.get('products') or data.get('lines', [])
        shipping_method = data.get('shipping_method')
        self._create_order_lines(order, user, products)

        self._create_shipping_order_line(order, shipping_method, user)
        
        return order

    def _find_or_create_address(self, user, parent_partner, addr_data, addr_type, id_type):
        """Busca o crea una dirección hija para el cliente"""
        if not addr_data or not isinstance(addr_data, dict):
            return parent_partner

        env = request.env(user=user.id)
        Partner = env['res.partner']
        Country = env['res.country']
        State = env['res.country.state']

        # Normalizar datos
        street = addr_data.get('address1')
        zip_code = addr_data.get('postcode')
        city = addr_data.get('city')
        country_code = addr_data.get('country') or 'EC'
        phone = addr_data.get('phone') or ''
        
        # Buscar país y estado
        country = Country.search([('code', '=', country_code)], limit=1)
        state_term = addr_data.get('state') or 'Pichincha';
        state = State.search([
            ('country_id', '=', country.id),
            '|', ('name', 'ilike', state_term), ('code', '=ilike', state_term)
        ], limit=1)

        # Criterio de búsqueda: Mismo padre y mismos datos de dirección clave
        domain = [
            ('parent_id', '=', parent_partner.id),
            ('type', '=', addr_type),
            ('street', '=', street),
            ('zip', '=', zip_code)
        ]
        
        existing = Partner.search(domain, limit=1)
        if existing:
            return existing

        
            
        # Crear nueva dirección
        name = f"{addr_data.get('firstname', '')} {addr_data.get('lastname', '')}".strip()
        
        new_addr_vals = {
            'parent_id': parent_partner.id,
            'type': addr_type,
            'name': name or parent_partner.name,
            'street': street,
            'company_name': 'Prestashop',
            'street2': addr_data.get('address2'),
            'city': city,
            'l10n_latam_identification_type_id': id_type,
            'zip': zip_code,
            'country_id': country.id if country else False,
            'state_id': state.id if state else False,
            'phone': phone,
            'vat': addr_data.get('vat') or parent_partner.vat, # A veces la dirección tiene su propio VAT
        }

        try:
            # Aislar errores de create para no dejar la transacción abortada.
            with request.env.cr.savepoint():
                return Partner.create(new_addr_vals)
        except Exception as e:
            _logger.exception(f"Error al crear dirección {new_addr_vals} - Error: {str(e)}")
            raise UserError(
                f"No se pudo crear la dirección {addr_type}. "
                f"Detalle: {e.__class__.__name__}: {str(e)}"
            )

    def _apply_shipping_method(self, order, method_name, cost):
        """Busca/Crea método de envío y agrega la línea de costo"""
        Product = request.env['product.product'].sudo()
        
        # Intentar buscar producto de envío existente por nombre exacto
        # Usamos un codigo interno fijo para reusarlo si es posible o creamos uno nuevo con el nombre del método
        
        # Buscar si ya existe un producto de servicio con este nombre exacto
        carrier_product = Product.search([
            ('name', '=', method_name), 
            ('type', '=', 'service')
        ], limit=1)
        
        if not carrier_product:
             carrier_product = Product.create({
                'name': method_name,
                'type': 'service',
                'list_price': cost,
                'sale_ok': True,
                'purchase_ok': False,
                # No ponemos default_code fijo para permitir múltiples métodos distintos
             })
             
        # Crear línea en la orden
        request.env['sale.order.line'].sudo().create({
            'order_id': order.id,
            'product_id': carrier_product.id,
            'name': f"Método de envío: {method_name}",
            'product_uom_qty': 1,
            'price_unit': cost,
             # 'is_delivery': True # Solo si 'delivery' está instalado, dejar comentado por seguridad si es base
        })

    def _update_order(self, order, user, data):
        """Actualiza una orden existente"""
        # Solo actualizar campos básicos, no recrear líneas
        update_vals = {}
        
        if data.get('note'):
            update_vals['note'] = data.get('note')
        
        if update_vals:
            order.write(update_vals)
        return order

    def _create_shipping_order_line(self, order, shipping_method, user):
        
        if not shipping_method or not isinstance(shipping_method, dict):
            return

        reference = shipping_method.get('reference')
        if not reference:
            return

        env = request.env(user=user.id)
        Product = env['product.product']
        SaleOrderLine = env['sale.order.line']

        product = Product.search([('default_code', '=', reference)], limit=1)
        if not product:
            raise UserError(
                f"No se encontró producto de envío con referencia '{reference}'"
            )

        SaleOrderLine.create({
            'order_id': order.id,
            'product_id': product.id,
            'name': shipping_method.get('name') or product.name,
            'product_uom_qty': 1,
            'price_unit': shipping_method.get('amount', 0.0),
        })

    def _create_order_lines(self, order, user, lines):
        """Crea las líneas de la orden"""
        env = request.env(user=user.id)
        SaleOrderLine = env['sale.order.line']
        Product = env['product.product']
        
        for line_data in lines:
            # Buscar producto por id o referencia
            product = None
        
            if line_data.get('product_id'):
                product = Product.browse(int(line_data.get('product_id')))
                if not product.exists():
                    product = None
            
            if not product and line_data.get('product_reference'):
                product = Product.search([
                    ('default_code', '=', line_data.get('product_reference'))
                ], limit=1)
            
            # Si no existe el producto, crear uno genérico
            doctor_id = line_data.get('doctor_id') or None

            if not product:
                product = self._create_generic_product(line_data, user)
            
            line_vals = {
                'order_id': order.id,
                'health_doctor_id': doctor_id,
                'product_id': product.id,
                'name': line_data.get('product_name') or product.name,
                'product_uom_qty': line_data.get('quantity', 1),
                'price_unit': line_data.get('unit_price', 0),
            }
            
            # Aplicar descuento si existe
            if line_data.get('discount_percent'):
                line_vals['discount'] = line_data.get('discount_percent')

            # Crear una línea por cada item recibido
            SaleOrderLine.create(line_vals)

    def _create_generic_product(self, line_data, user):
        """Crea un producto genérico cuando no existe"""
        ProductProduct = request.env(user=user.id)['product.product']
        
        return ProductProduct.create({
            'name': line_data.get('product_name', 'Producto PrestaShop'),
            'default_code': line_data.get('product_reference'),
            'type': 'consu',
            'list_price': line_data.get('unit_price', 0),
            'sale_ok': True,
            'purchase_ok': False,
        })

    @http.route('/api/v1/orders', type='http', auth='none', methods=['GET'], csrf=False)
    def get_orders(self):
        """Obtener lista de cotizaciones"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result

        try:
            orders = request.env['sale.order'].sudo().search([], order='create_date desc', limit=100)
            
            data = [{
                'odoo_id': o.id,
                'odoo_name': o.name,
                'reference': o.client_order_ref,
                'partner': o.partner_id.name,
                'date_order': o.date_order,
                'state': o.state,
                'amount_total': o.amount_total
            } for o in orders]
            
            return self._success_response(data=data)
            
        except Exception as e:
            return self._error_response(str(e), status=500)

    @http.route('/api/v1/orders/by_references', type='http', auth='none', methods=['POST'], csrf=False)
    def get_orders_by_references(self):
        """
        Obtener órdenes por lista de referencias (client_order_ref).

        Body JSON esperado:
        {
            "references": ["WVAVIRBJG", "ABC123", "..."]
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

        references = data.get('references') or []
        if not isinstance(references, list) or not references:
            return self._error_response("Se requiere 'references' como lista no vacía", status=400)

        # Normalizar: strings no vacíos y únicos, preservando orden
        clean_refs = []
        seen = set()
        for ref in references:
            if ref is None:
                continue
            ref_str = str(ref).strip()
            if not ref_str or ref_str in seen:
                continue
            seen.add(ref_str)
            clean_refs.append(ref_str)

        if not clean_refs:
            return self._error_response("No se proporcionaron referencias válidas", status=400)

        try:
            env = request.env(user=user.id)
            orders = env['sale.order'].search([
                ('client_order_ref', 'in', clean_refs)
            ], order='create_date desc')

            orders_by_ref = {}
            for order in orders:
                ref = order.client_order_ref
                # Si hay varias con la misma referencia, conservar la más reciente (ya ordenadas desc)
                if ref and ref not in orders_by_ref:
                    orders_by_ref[ref] = order

            found = []
            not_found = []
            for ref in clean_refs:
                order = orders_by_ref.get(ref)
                if not order:
                    not_found.append(ref)
                    continue

                lines = [{
                    'product': l.product_id.name,
                    'quantity': l.product_uom_qty,
                    'price_unit': l.price_unit,
                    'discount': l.discount,
                    'subtotal': l.price_subtotal,
                } for l in order.order_line]

                item = {
                    'odoo_id': order.id,
                    'odoo_name': order.name,
                    'reference': order.client_order_ref,
                    'partner': order.partner_id.name,
                    'date_order': order.date_order,
                    'state': order.state,
                    'amount_untaxed': order.amount_untaxed,
                    'amount_tax': order.amount_tax,
                    'amount_total': order.amount_total,
                    'lines': lines,
                }
                item.update(self._collect_invoice_response_for_order(order, None))
                found.append(item)

            return self._success_response(
                data={
                    'orders': found,
                    'found_count': len(found),
                    'not_found': not_found,
                    'not_found_count': len(not_found),
                },
                message=f"Encontradas {len(found)} de {len(clean_refs)} referencias"
            )
        except Exception as e:
            _logger.exception("Error en get_orders_by_references")
            return self._error_response(f"Error al buscar órdenes: {str(e)}", status=500)

    @http.route('/api/v1/orders/<int:odoo_id>', type='http', auth='none', 
                methods=['GET'], csrf=False)
    def get_order(self, odoo_id):
        """Obtener cotización por ID Odoo"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result

        order = request.env['sale.order'].sudo().browse(int(odoo_id))
        
        if not order.exists():
            return self._error_response("Orden no encontrada", status=404)
        
        lines = [{
            'product': l.product_id.name,
            'quantity': l.product_uom_qty,
            'price_unit': l.price_unit,
            'discount': l.discount,
            'subtotal': l.price_subtotal
        } for l in order.order_line]

        data = {
            'odoo_id': order.id,
            'odoo_name': order.name,
            'reference': order.client_order_ref,
            'partner': order.partner_id.name,
            'date_order': order.date_order,
            'state': order.state,
            'amount_untaxed': order.amount_untaxed,
            'amount_tax': order.amount_tax,
            'amount_total': order.amount_total,
            'lines': lines,
        }
        data.update(self._collect_invoice_response_for_order(order, None))

        return self._success_response(data=data)

    @http.route('/api/v1/orders/<int:odoo_id>/confirm', type='http', auth='none', 
                methods=['POST'], csrf=False)
    def confirm_order(self, odoo_id):
        """Confirmar cotización y convertirla en pedido de venta"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result

        order = request.env['sale.order'].sudo().browse(int(odoo_id))
        
        if not order.exists():
            return self._error_response("Orden no encontrada", status=404)
        
        if order.state != 'draft':
            return self._error_response(
                f"La orden no está en estado borrador. Estado actual: {order.state}",
                status=400
            )
        
        try:
            order.action_confirm()
            self._log_operation(
                'confirm', 'sale.order',
                record_id=order.id,
                status='success',
                message=f"Orden confirmada: {order.name}",
                user=user
            )
            
            return self._success_response(
                data={
                    'odoo_id': order.id,
                    'odoo_name': order.name,
                    'state': order.state
                },
                message="Orden confirmada correctamente"
            )
        except Exception as e:
            return self._error_response(f"Error al confirmar: {str(e)}", status=500)

    @http.route('/api/v1/orders/<int:odoo_id>/cancel', type='http', auth='none', methods=['POST'], csrf=False)
    def cancel_order(self, odoo_id):
        """Cancelar cotización"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result

        order = request.env['sale.order'].sudo().browse(int(odoo_id))
        
        if not order.exists():
            return self._error_response("Orden no encontrada", status=404)
        
        try:
            order.action_cancel()
            self._log_operation(
                'cancel', 'sale.order',
                record_id=order.id,
                status='success',
                message=f"Orden cancelada: {order.name}",
                user=user
            )
            
            return self._success_response(
                data={
                    'odoo_id': order.id,
                    'odoo_name': order.name,
                    'state': order.state
                },
                message="Orden cancelada correctamente"
            )
        except Exception as e:
            return self._error_response(f"Error al cancelar: {str(e)}", status=500)
            
