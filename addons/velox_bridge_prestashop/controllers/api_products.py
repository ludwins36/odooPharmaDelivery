# -*- coding: utf-8 -*-

import base64
import json
import logging
from odoo import http
from odoo.http import request
from .main import VeloxBridgeController

_logger = logging.getLogger(__name__)

# Tags de producto: al menos uno debe estar en tags_value del producto
TAGS_UNIDADES = ['UNIDADES']
TAGS_CADENA_FRINO = ['REFRIGERADO']


class ProductsAPIController(VeloxBridgeController):
    """API para gestión de productos"""

    def _compute_price_with_tax(self, product, price_no_tax):
        """Precio con impuestos de venta del producto, si aplican."""
        taxes = product.taxes_id
        if not taxes:
            return round(price_no_tax, 2)
        # PVP con impuestos incluidos en list_price
        if any(getattr(tax, 'price_include', False) for tax in taxes):
            return round(product.list_price, 2)
        total = price_no_tax
        for tax in taxes:
            if tax.amount_type == 'percent':
                total += price_no_tax * (tax.amount / 100.0)
            elif tax.amount_type == 'fixed':
                total += tax.amount
        return round(total, 2)

    @http.route('/api/v1/products', type='http', auth='none', methods=['POST'], csrf=False)
    def create_product(self):
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
            product = self._process_product(user, data)
            self._log_operation(
                'import', 'product.template',
                record_id=product.id,
                status='success',
                message=f"Producto creado/actualizado: {data.get('name')}",
                user=user
            )
            
            return self._success_response(
                data={
                    'odoo_id': product.id,
                    'reference': product.default_code
                },
                message="Producto procesado correctamente"
            )
            
        except Exception as e:
            _logger.exception("Error al procesar producto")
            self._log_operation(
                'import', 'product.template',
                status='error',
                message=str(e),
                user=user
            )
            return self._error_response(f"Error al procesar producto: {str(e)}", status=500)

    def _process_product(self, user, data):
        """Procesa y crea/actualiza el producto"""
        ProductTemplate = request.env['product.template'].sudo()
        
        # Buscar producto existente por `odoo_id` si se proporcionó, sino por referencia
        existing = None
        if data.get('odoo_id'):
            try:
                existing = ProductTemplate.sudo().browse(int(data.get('odoo_id')))
                if not existing.exists():
                    existing = None
            except Exception:
                existing = None
        if not existing and data.get('reference'):
            existing = ProductTemplate.search([
                ('default_code', '=', data.get('reference'))
            ], limit=1)
        
        # Buscar categoría si se proporciona
        category_id = False
        if data.get('category_id'):
            try:
                category = request.env['product.category'].sudo().browse(int(data.get('category_id')))
                if category.exists():
                    category_id = category.id
            except Exception:
                category_id = False

        vals = {
            'name': data.get('name'),
            'default_code': data.get('reference'),
            'description': data.get('description'),
            'list_price': data.get('price', 0.0),
            'standard_price': data.get('cost', 0.0),
            'weight': data.get('weight', 0.0),
            'active': data.get('active', True),
            'type': 'consu',  # Consumible por defecto
            'sale_ok': True,
            'purchase_ok': True,
        }
        
        if category_id:
            vals['categ_id'] = category_id

        if existing:
            existing.write(vals)
            return existing
        else:
            return ProductTemplate.create(vals)

    @http.route('/api/v1/products', type='http', auth='none', methods=['GET'], csrf=False)
    def get_products(self):
        """
        Obtener lista de productos con sus combinaciones para que el cliente mapee.
        Parámetros de paginación (query string):
            limit: cantidad por página (default 50, máx 500). Si limit=0 se devuelven todos.
            page: número de página, desde 1 (default 1). Con limit=0 se ignora.
        """
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        user = result
        
        # Parámetros de paginación
        try:
            limit_param = int(request.httprequest.args.get('limit', 50))
        except (TypeError, ValueError):
            limit_param = 50
        # limit=0 significa "todos los productos" (sin paginación)
        if limit_param == 0:
            limit = 0   # sin límite
            page = 1
            offset = 0
        else:
            limit = min(limit_param, 500)
            limit = max(1, limit)
            try:
                page = max(1, int(request.httprequest.args.get('page', 1)))
            except (TypeError, ValueError):
                page = 1
            offset = (page - 1) * limit
        
        try:
            domain = [('sale_ok', '=', True)]
            warehouse = request.env['stock.warehouse'].sudo().browse(2)
            if not warehouse.exists() or not warehouse.view_location_id:
                return self._error_response("Almacén 2 no encontrado o sin ubicación raíz configurada", status=400)

            # Total de registros (para calcular páginas)
            total = request.env['product.template'].sudo().search_count(domain)
            # Buscamos los templates (con o sin paginación)
            if limit == 0:
                templates = request.env['product.template'].sudo().search(domain)
            else:
                templates = request.env['product.template'].sudo().search(
                    domain, limit=limit, offset=offset
                )
            
            output = []
            
            # Pre-calcular stock solo del almacén id=2 (ubicación raíz y sububicaciones internas)
            all_variants = templates.mapped('product_variant_ids')
            stock_data = request.env['stock.quant'].sudo().read_group(
                [
                    ('product_id', 'in', all_variants.ids),
                    ('location_id', 'child_of', warehouse.view_location_id.id),
                    ('location_id.usage', '=', 'internal'),
                ],
                ['product_id', 'quantity'],
                ['product_id']
            )
            stock_map = {item['product_id'][0]: item['quantity'] for item in stock_data}

            for pt in templates:
                # Extraer variantes (combinaciones)
                combinations = []
                tmpl_stock = 0.0
                for variant in pt.product_variant_ids:
                    qty = stock_map.get(variant.id, 0.0)
                    tmpl_stock += qty
                    combinations.append({
                        'odoo_variant_id': variant.id,
                        'reference': variant.default_code or pt.default_code,
                        'price_extra': variant.lst_price - pt.list_price, # Diferencia de precio
                        'weight': variant.weight,
                        'barcode': variant.barcode,
                        'stock_quantity': qty,
                        'attributes': [{
                            'name': val.attribute_id.name,
                            'value': val.name
                        } for val in variant.product_template_attribute_value_ids]
                    })

                product_taxes = []
                price_no_tax = pt.list_price
                taxes = pt.taxes_id

                for tax in taxes:
                    product_taxes.append({
                        'id': tax.id,
                        'name': tax.name,
                        'amount': tax.amount,            # El porcentaje (ej: 16.0 o 21.0)
                        'price_include': tax.price_include, # True si el PVP ya tiene el IVA
                        'amount_type': tax.amount_type   # 'percent', 'fixed', etc.
                    })

                # Si algún product.tag tiene visible_on_ecommerce=False, enviar active=False
                active = pt.active
                tag_ids = getattr(pt, 'product_tag_ids', None)
                is_visible_on_ecommerce = True
                pmf = {
                    'qty': pt.health_fmp_rule_quantity if pt.health_fmp_rule_quantity else 0,
                    'promo': pt.health_fmp_promo_quantity if pt.health_fmp_promo_quantity else 0
                }

                componentes_nombres = []

                if pt.health_product_component_ids:
                    for line in pt.health_product_component_ids:
                    # En los modelos de Odoo, 'display_name' suele traer el nombre formateado
                    # Si no funciona, prueba con: line.component_id.name (depende de la definición del modelo)
                        nombre = line.display_name or ""
                        if nombre:
                            componentes_nombres.append(nombre)

                principios_activos = ", ".join(componentes_nombres)

                especifications = {
                    'indications' : pt.health_product_indications,
                    'contraindications' : pt.health_product_contraindications,
                    'side_effects' : pt.health_product_side_effects,
                    'dosage' : pt.health_product_dosage,
                    'principios_activos' : principios_activos if principios_activos else False,
                }
                

                if tag_ids:
                    if any(not getattr(tag, 'visible_on_ecommerce', True) for tag in tag_ids):
                        active = False
                        is_visible_on_ecommerce = False

                tags_value = tag_ids.mapped('display_name') if tag_ids else []

                output.append({
                    'odoo_template_id': pt.id,
                    'name': pt.name,
                    'reference': pt.default_code,
                    'is_visible_on_ecommerce': is_visible_on_ecommerce,
                    'tag_ids': tag_ids,
                    'description': pt.description_sale or '',
                    'price': round(price_no_tax, 3),
                    'stock_quantity': tmpl_stock,
                    'category': pt.public_categ_ids.mapped('display_name'),
                    'is_farmacy': pt.health_fmp,
                    'pmf': pmf,
                    'especifications': especifications,
                    # 'image': pt.image_1920,
                    'has_variants': pt.has_configurable_attributes,
                    'active': active,
                    'taxes': product_taxes,
                    'tags': tags_value,
                    'is_unidades': any(tag in tags_value for tag in TAGS_UNIDADES),
                    'is_cadena_frino': any(tag in tags_value for tag in TAGS_CADENA_FRINO),
                    'prescription': pt.health_product_prescription_type,
                    'variants': combinations,
                })
            
            total_pages = 1 if limit == 0 else ((total + limit - 1) // limit)
            return self._success_response(data={
                'products': output,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'total_pages': total_pages,
                },
            })
            
        except Exception as e:
            _logger.error(f"Error en GET products: {str(e)}")
            return self._error_response(f"Error en GET products: {str(e)}", status=500)
        

    @http.route('/api/v1/products/<int:odoo_id>', type='http', auth='none', 
                methods=['GET'], csrf=False)
    def get_product(self, odoo_id):
        """Obtener producto por id de Odoo"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        user = result

        product = request.env['product.template'].sudo().browse(int(odoo_id))
        if not product.exists():
            return self._error_response("Producto no encontrado", status=404)
        
        if not product:
            return self._error_response("Producto no encontrado", status=404)
        
        warehouse = request.env['stock.warehouse'].sudo().browse(2)
        if not warehouse.exists() or not warehouse.view_location_id:
            return self._error_response("Almacén 2 no encontrado o sin ubicación raíz configurada", status=400)

        # Calcular stock solo del almacén id=2 (ubicación raíz y sububicaciones internas)
        stock_qty = sum(request.env['stock.quant'].sudo().search([
            ('product_id.product_tmpl_id', '=', product.id),
            ('location_id', 'child_of', warehouse.view_location_id.id),
            ('location_id.usage', '=', 'internal')
        ]).mapped('quantity'))

        # Calcular precio sin impuestos (si price_include, quitar impuestos)
        price_no_tax = product.list_price
        for tax in product.taxes_id:
            if tax.price_include and tax.amount_type == 'percent':
                price_no_tax = price_no_tax / (1 + (tax.amount / 100.0))

        price_with_tax = self._compute_price_with_tax(product, price_no_tax)

        image_value = None
        tags_value = product.product_tag_ids.mapped('display_name')

        product_taxes = []
        for tax in product.taxes_id:
            product_taxes.append({
                'id': tax.id,
                'name': tax.name,
                'amount': tax.amount,            # El porcentaje (ej: 16.0 o 21.0)
                'price_include': tax.price_include, # True si el PVP ya tiene el IVA
                'amount_type': tax.amount_type   # 'percent', 'fixed', etc.
            })


        if product.image_1920:
            raw_val = product.image_1920

            if isinstance(raw_val, bytes):
                try:
                    # Si viene como bytes del texto base64 (lo típico en Odoo a veces)
                    b64 = raw_val.decode('ascii')
                except Exception:
                    # Si realmente viene como bytes binarios de la imagen
                    b64 = base64.b64encode(raw_val).decode('ascii')
            elif isinstance(raw_val, str):
                b64 = raw_val
            else:
                b64 = ''

            if b64:
                image_value = 'data:image/png;base64,' + b64

        return self._success_response(data={
            'odoo_id': product.id,
            'reference': product.default_code,
            'name': product.name,
            'description': product.description,
            'price': round(price_no_tax, 3),
            'price_with_tax': round(price_with_tax, 3),
            'stock_quantity': stock_qty,
            'cost': product.standard_price, 
            'category': product.public_categ_ids.mapped('display_name'),
            'tags': product.product_tag_ids.mapped('display_name'),
            'taxes': product_taxes,
            'image': image_value,
            'is_unidades': any(tag in tags_value for tag in TAGS_UNIDADES),
            'is_cadena_frino': any(tag in tags_value for tag in TAGS_CADENA_FRINO),
            'prescription': product.health_product_prescription_type,
            'discount_max_percentage': getattr(product, 'l10n_latam_price_discount_max_percentage', 0.0),
            'active': product.active
        })

    @http.route('/api/v1/products/bulk', type='http', auth='none', 
                methods=['POST'], csrf=False)
    def bulk_create_products(self):
        """
        Crear múltiples productos en lote
        
        Body JSON esperado:
        {
            "products": [
                {...producto1...},
                {...producto2...}
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

        products = data.get('products', [])
        if not products:
            return self._error_response("No se proporcionaron productos")

        results = []
        errors = []
        
        for product_data in products:
            try:
                product = self._process_product(user, product_data)
                results.append({
                    'odoo_id': product.id,
                    'status': 'success'
                })
            except Exception as e:
                errors.append({
                    'odoo_id': product_data.get('odoo_id'),
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
            message=f"Procesados {len(results)} productos, {len(errors)} errores"
        )
