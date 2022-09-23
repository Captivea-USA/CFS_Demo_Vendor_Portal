from odoo import models, fields, api

class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # EOI-400: Fix auto-population default tax id on PO order lines
    @api.onchange("product_id")
    def _compute_tax_id(self):
        super(PurchaseOrderLine, self)._compute_tax_id()
        if self.order_id.cfs_default_product_line_tax:
            self.taxes_id = self.order_id.cfs_default_product_line_tax