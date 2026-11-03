# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
    """Extensión de contactos para PrestaShop"""
    _inherit = 'res.partner'

    # Removed PrestaShop-specific fields; integration will use Odoo record ids
