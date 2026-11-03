# -*- coding: utf-8 -*-

import json
from odoo import http
from odoo.http import request
from .main import VeloxBridgeController

class PaymentMethodsAPIController(VeloxBridgeController):
    """API para métodos de pago"""

    @http.route('/api/v1/payment_methods', type='http', auth='none', methods=['GET'], csrf=False)
    def get_payment_methods(self):
        """Devuelve una lista de métodos de pago activos"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result
        PaymentTerm = request.env['l10n_latam.sale.payment.method'].sudo()
        payment_terms = PaymentTerm.search([])
        data = [
            {
                'id': pt.id,
                'name': pt.name,
            }
            for pt in payment_terms
        ]
        return self._success_response(data=data)

    @http.route('/api/v1/payment_methods/<int:payment_id>', type='http', auth='none', methods=['GET'], csrf=False)
    def get_payment_method(self, payment_id):
        """Devuelve un método de pago por ID"""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)
        
        user = result
        PaymentTerm = request.env['l10n_latam.sale.payment.method'].sudo()
        pt = PaymentTerm.browse(payment_id)
        if not pt.exists() or not pt.active:
            return self._error_response('Método de pago no encontrado o inactivo', status=404)
        data = {
            'id': pt.id,
            'name': pt.name,
        }
        return self._success_response(data=data)

    @http.route('/api/v1/invoice_payments', type='http', auth='none', methods=['GET'], csrf=False)
    def get_invoice_payments(self):
        """Devuelve lista de l10n_latam.sale.invoice.payment con journal_id (many2one)."""
        valid, result = self._validate_api_key()
        if not valid:
            return self._error_response(result, status=401)

        user = result
        InvoicePayment = request.env['l10n_latam.sale.invoice.payment'].sudo()
        invoice_payments = InvoicePayment.search([])

        data = []
        for ip in invoice_payments:
            data.append({
                'id': ip.id,
                'name': ip.display_name or ip.name,
                'journal_id': ip.journal_id.id if ip.journal_id else False,
                'journal_name': ip.journal_id.name if ip.journal_id else False,
            })

        return self._success_response(data=data)
