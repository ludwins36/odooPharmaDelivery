# -*- coding: utf-8 -*-

import logging
from odoo import http
from odoo.http import request
from .main import VeloxBridgeController

_logger = logging.getLogger(__name__)


class DiscountsAPIController(VeloxBridgeController):
    """API para gestión de descuentos (Listas de precios)"""

    @http.route('/api/v1/discounts', type='http', auth='none', methods=['GET'], csrf=False)
    def get_discounts(self):
        """
        Obtener lista de descuentos (Listas de Precios).
        Retorna las listas de precios activas y sus reglas.
        """
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        try:
            # Obtenemos las listas de precios
            pricelist_model = request.env['product.pricelist'].sudo()
            
            # Buscar listas de precios activas
            # Si se desea filtrar, se puede añadir domain. Por defecto active=True está implícito
            pricelists = pricelist_model.search([])
            
            discounts_list = []
            
            for pl in pricelists:
                items_data = []
                for item in pl.item_ids:
                    item_info = {
                        'id': item.id,
                        'applied_on': item.applied_on, # '3_global', '2_product_category', '1_product', '0_product_variant'
                        'min_quantity': item.min_quantity,
                        'date_start': item.date_start,
                        'date_end': item.date_end,
                        'compute_price': item.compute_price, # 'fixed', 'percentage', 'formula'
                    }
                    
                    # Detalles específicos según el tipo de aplicación
                    if item.applied_on == '2_product_category' and item.categ_id:
                        item_info['category_id'] = item.categ_id.id
                        item_info['category_name'] = item.categ_id.name
                    elif item.applied_on == '1_product' and item.product_tmpl_id:
                        item_info['product_tmpl_id'] = item.product_tmpl_id.id
                        item_info['product_name'] = item.product_tmpl_id.name
                    elif item.applied_on == '0_product_variant' and item.product_id:
                        item_info['product_id'] = item.product_id.id
                        item_info['product_name'] = item.product_id.display_name

                    # Detalles del cálculo del precio
                    if item.compute_price == 'fixed':
                        item_info['fixed_price'] = item.fixed_price
                    elif item.compute_price == 'percentage':
                        item_info['percent_price'] = item.percent_price
                    
                    items_data.append(item_info)

                discounts_list.append({
                    'id': pl.id,
                    'name': pl.name,
                    'currency_id': pl.currency_id.id,
                    'currency_name': pl.currency_id.name,
                    'active': pl.active,
                    'items': items_data
                })

            return self._success_response(
                data={
                    'count': len(discounts_list),
                    'discounts': discounts_list
                },
                message="Lista de descuentos obtenida correctamente"
            )

        except Exception as e:
            _logger.exception("Error al obtener descuentos")
            return self._error_response(f"Error al obtener descuentos: {str(e)}", status=500)

    @http.route('/api/v1/discounts/<int:discount_id>', type='http', auth='none', methods=['GET'], csrf=False)
    def get_discount(self, discount_id):
        """
        Obtener un descuento específico por ID.
        """
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        try:
            pl = request.env['product.pricelist'].sudo().browse(discount_id)
            
            if not pl.exists():
                return self._error_response("Descuento no encontrado", status=404)

            # Formatear datos (misma lógica que en lista)
            items_data = []
            for item in pl.item_ids:
                item_info = {
                    'id': item.id,
                    'applied_on': item.applied_on,
                    'min_quantity': item.min_quantity,
                    'date_start': item.date_start,
                    'date_end': item.date_end,
                    'compute_price': item.compute_price,
                }
                
                if item.applied_on == '2_product_category' and item.categ_id:
                    item_info['category_id'] = item.categ_id.id
                    item_info['category_name'] = item.categ_id.name
                elif item.applied_on == '1_product' and item.product_tmpl_id:
                    item_info['product_tmpl_id'] = item.product_tmpl_id.id
                    item_info['product_name'] = item.product_tmpl_id.name
                elif item.applied_on == '0_product_variant' and item.product_id:
                    item_info['product_id'] = item.product_id.id
                    item_info['product_name'] = item.product_id.display_name

                if item.compute_price == 'fixed':
                    item_info['fixed_price'] = item.fixed_price
                elif item.compute_price == 'percentage':
                    item_info['percent_price'] = item.percent_price
                
                items_data.append(item_info)

            data = {
                'id': pl.id,
                'name': pl.name,
                'currency_id': pl.currency_id.id,
                'currency_name': pl.currency_id.name,
                'active': pl.active,
                'items': items_data
            }
            
            return self._success_response(
                data=data,
                message="Descuento obtenido correctamente"
            )

        except Exception as e:
            _logger.exception("Error al obtener el descuento %s", discount_id)
            return self._error_response(f"Error al obtener el descuento: {str(e)}", status=500)
