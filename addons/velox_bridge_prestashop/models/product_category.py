# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductCategory(models.Model):
    """Extensión de categoría de producto para PrestaShop"""
    _inherit = 'product.category'

    # Removed PrestaShop-specific fields; integration will use Odoo record ids
