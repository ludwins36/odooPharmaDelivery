# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductAttribute(models.Model):
    """Extensión de atributo de producto para PrestaShop"""
    _inherit = 'product.attribute'

    # Removed PrestaShop-specific fields; integration will use Odoo record ids


class ProductAttributeValue(models.Model):
    """Extensión de valor de atributo para PrestaShop"""
    _inherit = 'product.attribute.value'

    # Removed PrestaShop-specific fields; integration will use Odoo record ids
