# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PrestashopLog(models.Model):
    """Registro de operaciones de sincronización"""
    _name = 'prestashop.log'
    _description = 'Log de Sincronización PrestaShop'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', string='Usuario', readonly=True)
    operation = fields.Selection([
        ('import', 'Importar'),
        ('export', 'Exportar'),
        ('confirm', 'Confirmar'),
        ('cancel', 'Cancelar'),
        ('update', 'Actualizar'),
    ], string='Operación', required=True)
    model = fields.Char(string='Modelo')
    record_id = fields.Integer(string='ID Registro Odoo')
    status = fields.Selection([
        ('success', 'Éxito'),
        ('error', 'Error'),
        ('warning', 'Advertencia'),
    ], string='Estado', required=True, default='success')
    message = fields.Text(string='Mensaje')
    
    create_date = fields.Datetime(string='Fecha', readonly=True)
    create_uid = fields.Many2one('res.users', string='Usuario', readonly=True)

    def action_view_record(self):
        """Ver registro relacionado"""
        self.ensure_one()
        if not self.model or not self.record_id:
            return
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.model,
            'res_id': self.record_id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.autovacuum
    def _gc_old_logs(self):
        """Limpieza automática de logs antiguos (más de 30 días)"""
        limit_date = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        self.search([('create_date', '<', limit_date)]).unlink()
