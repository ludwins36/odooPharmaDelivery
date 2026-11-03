# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleOrder(models.Model):
    """Extensión de pedido de venta para PrestaShop"""
    _inherit = 'sale.order'

    # Removed PrestaShop-specific fields; integration will use Odoo record ids
