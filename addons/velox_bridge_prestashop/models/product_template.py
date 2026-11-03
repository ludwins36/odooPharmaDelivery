# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProductTemplate(models.Model):
    """Extensión de plantilla de producto para PrestaShop"""
    _inherit = 'product.template'

    # Removed PrestaShop-specific fields; integration will use Odoo record ids
