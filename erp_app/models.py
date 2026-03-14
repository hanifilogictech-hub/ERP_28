from django.db import models

# Create your models here.
from django.db import models


class PurchaseOrder(models.Model):
    order_no = models.CharField(max_length=64, unique=True)
    order_date = models.DateField()
    invoice_no = models.CharField(max_length=64)
    supplier = models.CharField(max_length=128)
    amount = models.FloatField()
    paid_amount = models.FloatField(default=0)
    supplier_code = models.CharField(max_length=32, default="", blank=True)
    warehouse = models.CharField(max_length=128, default="", blank=True)
    payment_terms = models.CharField(max_length=64, default="", blank=True)
    currency = models.CharField(max_length=16, default="", blank=True)
    status = models.CharField(max_length=32, default="Draft", blank=True)

    class Meta:
        db_table = "purchase_orders"

class SalesQuotation(models.Model):
    tran_no = models.CharField(max_length=50)
    tran_date = models.DateField()
    customer_name = models.CharField(max_length=150)
    remarks = models.TextField(blank=True, null=True)
    total_amount = models.FloatField(default=0)
    approved = models.BooleanField(default=False)

    class Meta:
        db_table = "sales_quotations"

    def __str__(self):
        return self.tran_no


class SalesQuotationItem(models.Model):
    quotation = models.ForeignKey(
        SalesQuotation,
        on_delete=models.CASCADE,
        related_name="items"
    )
    product_code = models.CharField(max_length=50)
    product_name = models.CharField(max_length=150)
    qty = models.FloatField()
    price = models.FloatField()
    total = models.FloatField()

    class Meta:
        db_table = "sales_quotation_items"



class SalesOrder(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("progress", "In Progress"),
        ("closed", "Closed"),
    ]

    order_no = models.CharField(max_length=64)
    order_date = models.DateField()
    invoice_no = models.CharField(max_length=64)
    customer = models.CharField(max_length=128)
    amount = models.FloatField()
    paid_amount = models.FloatField(default=0)
    salesman = models.CharField(max_length=64, default="Salesman 1")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open"
    )

    # ✅ ADD THIS
    printed = models.BooleanField(default=False)

    class Meta:
        db_table = "sales_orders"

        
class Delivery(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("closed", "Closed"),
    ]

    tran_no = models.CharField(max_length=50)
    tran_date = models.DateField()
    customer = models.CharField(max_length=150)
    sub_total = models.FloatField(default=0)
    tax = models.FloatField(default=0)
    net_total = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")

    class Meta:
        db_table = "deliveries"        


class PurchaseInvoice(models.Model):
    invoice_no = models.CharField(max_length=64)
    invoice_date = models.DateField()
    supplier = models.CharField(max_length=128)
    total_amount = models.FloatField()
    paid_amount = models.FloatField(default=0)

    class Meta:
        db_table = "purchase_invoices"


class SalesInvoice(models.Model):
    invoice_no = models.CharField(max_length=64)
    invoice_date = models.DateField()
    customer = models.CharField(max_length=128)
    total_amount = models.FloatField()
    paid_amount = models.FloatField(default=0)

    class Meta:
        db_table = "sales_invoices"


class Product(models.Model):
    product_name = models.CharField(max_length=128)
    department = models.CharField(max_length=64)
    category = models.CharField(max_length=64)
    cost_price = models.FloatField()
    sell_price = models.FloatField()
    stock_qty = models.IntegerField()
    reorder_qty = models.IntegerField(default=10)

    class Meta:
        db_table = "products"


class SalesOrderItem(models.Model):
    sales_order = models.ForeignKey(
        "erp_app.SalesOrder",
        on_delete=models.CASCADE,
        db_column="sales_order_id",
        related_name="items",
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, db_column="product_id", related_name="order_items"
    )
    qty = models.IntegerField()
    amount = models.FloatField()

    class Meta:
        db_table = "sales_order_items"


class SupplierMaster(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=128)
    contact = models.CharField(max_length=128, default="", blank=True)
    address = models.CharField(max_length=255, default="", blank=True)
    country = models.CharField(max_length=64, default="", blank=True)
    currency = models.CharField(max_length=16, default="INR", blank=True)
    payment_terms = models.CharField(max_length=64, default="Net 30", blank=True)

    class Meta:
        db_table = "supplier_master"


class WarehouseMaster(models.Model):
    name = models.CharField(max_length=128, unique=True)

    class Meta:
        db_table = "warehouse_master"


class PurchaseProduct(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=255, default="", blank=True)
    unit_price = models.FloatField(default=0)
    tax_percent = models.FloatField(default=0)

    class Meta:
        db_table = "purchase_products"


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        db_column="purchase_order_id",
        related_name="po_items",
    )
    product_code = models.CharField(max_length=32, default="", blank=True)
    product_name = models.CharField(max_length=128)
    description = models.CharField(max_length=255, default="", blank=True)
    qty = models.FloatField(default=0)
    unit_price = models.FloatField(default=0)
    discount_percent = models.FloatField(default=0)
    tax_percent = models.FloatField(default=0)
    line_total = models.FloatField(default=0)
    net_total = models.FloatField(default=0)

    class Meta:
        db_table = "purchase_order_items"


class Inventory(models.Model):
    product_code = models.CharField(max_length=32)
    product_name = models.CharField(max_length=128, default="", blank=True)
    location = models.CharField(max_length=128, default="", blank=True)
    stock_qty = models.FloatField(default=0)

    class Meta:
        db_table = "inventory"
        constraints = [
            models.UniqueConstraint(
                fields=["product_code", "location"], name="uniq_inventory_product_location"
            )
        ]


class GoodsReceipt(models.Model):
    gr_no = models.CharField(max_length=64, unique=True)
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        db_column="purchase_order_id",
        related_name="goods_receipts",
    )
    receipt_date = models.DateField()
    invoice_no = models.CharField(max_length=64, default="", blank=True)
    supplier = models.CharField(max_length=128, default="", blank=True)
    location = models.CharField(max_length=128, default="", blank=True)
    status = models.CharField(max_length=32, default="Open")

    class Meta:
        db_table = "goods_receipts"


class GoodsReceiptItem(models.Model):
    goods_receipt = models.ForeignKey(
        GoodsReceipt,
        on_delete=models.CASCADE,
        db_column="goods_receipt_id",
        related_name="items",
    )
    po_item = models.ForeignKey(
        PurchaseOrderItem,
        on_delete=models.PROTECT,
        db_column="po_item_id",
        null=True,
        blank=True,
        related_name="receipt_items",
    )
    product_code = models.CharField(max_length=32, default="", blank=True)
    product_name = models.CharField(max_length=128, default="", blank=True)
    ordered_qty = models.FloatField(default=0)
    received_qty = models.FloatField(default=0)
    accepted_qty = models.FloatField(default=0)
    damaged_qty = models.FloatField(default=0)
    quality_status = models.CharField(max_length=16, default="Pass")
    unit_price = models.FloatField(default=0)
    tax_percent = models.FloatField(default=0)
    line_total = models.FloatField(default=0)
    net_total = models.FloatField(default=0)
    is_over_delivery = models.BooleanField(default=False)

    class Meta:
        db_table = "goods_receipt_items"


class GoodsReturn(models.Model):
    return_no = models.CharField(max_length=64, unique=True)
    original_gr = models.ForeignKey(
        GoodsReceipt,
        on_delete=models.PROTECT,
        db_column="original_gr_id",
        related_name="goods_returns",
    )
    supplier = models.CharField(max_length=128, default="", blank=True)
    return_date = models.DateField()
    invoice_no = models.CharField(max_length=64, default="", blank=True)
    location = models.CharField(max_length=128, default="", blank=True)
    status = models.CharField(max_length=64, default="Pending Vendor Confirmation")
    total_amount = models.FloatField(default=0)

    class Meta:
        db_table = "goods_returns"


class GoodsReturnItem(models.Model):
    goods_return = models.ForeignKey(
        GoodsReturn,
        on_delete=models.CASCADE,
        db_column="goods_return_id",
        related_name="items",
    )
    source_gr_item = models.ForeignKey(
        GoodsReceiptItem,
        on_delete=models.PROTECT,
        db_column="source_gr_item_id",
        related_name="return_items",
    )
    product_code = models.CharField(max_length=32, default="", blank=True)
    product_name = models.CharField(max_length=128, default="", blank=True)
    quantity = models.FloatField(default=0)
    reason = models.CharField(max_length=128, default="", blank=True)
    condition = models.CharField(max_length=64, default="Damaged")
    unit_price = models.FloatField(default=0)
    tax_percent = models.FloatField(default=0)
    line_total = models.FloatField(default=0)
    net_total = models.FloatField(default=0)

    class Meta:
        db_table = "goods_return_items"


class DebitNote(models.Model):
    note_no = models.CharField(max_length=64, unique=True)
    goods_return = models.OneToOneField(
        GoodsReturn,
        on_delete=models.CASCADE,
        db_column="goods_return_id",
        related_name="debit_note",
    )
    supplier = models.CharField(max_length=128, default="", blank=True)
    note_date = models.DateField()
    amount = models.FloatField(default=0)
    status = models.CharField(max_length=32, default="Open")

    class Meta:
        db_table = "debit_notes"


class SupplierLedgerEntry(models.Model):
    supplier = models.CharField(max_length=128, default="", blank=True)
    entry_date = models.DateField()
    document_type = models.CharField(max_length=64, default="")
    document_no = models.CharField(max_length=64, default="")
    amount = models.FloatField(default=0)
    dr_cr = models.CharField(max_length=8, default="CR")
    remarks = models.CharField(max_length=255, default="", blank=True)

    class Meta:
        db_table = "supplier_ledger"


class PurchaseInvoiceEntry(models.Model):
    tran_no = models.CharField(max_length=64, unique=True)
    po_no = models.CharField(max_length=64, default="", blank=True)
    gr_no = models.CharField(max_length=64, default="", blank=True)
    supplier_invoice_no = models.CharField(max_length=64, unique=True)
    invoice_date = models.DateField()
    supplier = models.CharField(max_length=128, default="", blank=True)
    location = models.CharField(max_length=128, default="", blank=True)
    status = models.CharField(max_length=32, default="Approved")
    payment_status = models.CharField(max_length=32, default="Not Paid")
    sub_total = models.FloatField(default=0)
    tax_total = models.FloatField(default=0)
    net_total = models.FloatField(default=0)
    paid_amount = models.FloatField(default=0)
    balance_amount = models.FloatField(default=0)

    class Meta:
        db_table = "purchase_invoice_entries"


class PurchaseInvoiceEntryItem(models.Model):
    invoice_entry = models.ForeignKey(
        PurchaseInvoiceEntry,
        on_delete=models.CASCADE,
        db_column="invoice_entry_id",
        related_name="items",
    )
    gr_item = models.ForeignKey(
        GoodsReceiptItem,
        on_delete=models.PROTECT,
        db_column="gr_item_id",
        related_name="invoice_items",
    )
    po_item = models.ForeignKey(
        PurchaseOrderItem,
        on_delete=models.PROTECT,
        db_column="po_item_id",
        related_name="invoice_items",
        null=True,
        blank=True,
    )
    product_code = models.CharField(max_length=32, default="", blank=True)
    product_name = models.CharField(max_length=128, default="", blank=True)
    billed_qty = models.FloatField(default=0)
    unit_price = models.FloatField(default=0)
    tax_percent = models.FloatField(default=0)
    sub_total = models.FloatField(default=0)
    net_total = models.FloatField(default=0)

    class Meta:
        db_table = "purchase_invoice_entry_items"


class StockRequest(models.Model):
    request_no = models.CharField(max_length=64, unique=True)
    request_date = models.DateField()
    from_location = models.CharField(max_length=128, default="", blank=True)
    to_location = models.CharField(max_length=128, default="", blank=True)
    status = models.CharField(max_length=32, default="Pending Approval")
    remarks = models.CharField(max_length=255, default="", blank=True)
    created_by = models.CharField(max_length=64, default="Admin", blank=True)
    created_date = models.DateField()

    class Meta:
        db_table = "stock_requests"


class StockRequestItem(models.Model):
    stock_request = models.ForeignKey(
        StockRequest,
        on_delete=models.CASCADE,
        db_column="stock_request_id",
        related_name="items",
    )
    product_code = models.CharField(max_length=32, default="", blank=True)
    product_name = models.CharField(max_length=128, default="", blank=True)
    carton_qty = models.FloatField(default=0)
    loose_qty = models.FloatField(default=0)
    total_qty = models.FloatField(default=0)

    class Meta:
        db_table = "stock_request_items"


class StockTransfer(models.Model):
    transfer_no = models.CharField(max_length=64, unique=True)
    transfer_date = models.DateField()
    from_location = models.CharField(max_length=128, default="", blank=True)
    to_location = models.CharField(max_length=128, default="", blank=True)
    status = models.CharField(max_length=32, default="Draft")
    remarks = models.CharField(max_length=255, default="", blank=True)
    has_discrepancy = models.BooleanField(default=False)
    discrepancy_remarks = models.CharField(max_length=255, default="", blank=True)

    class Meta:
        db_table = "stock_transfers"


class StockTransferItem(models.Model):
    stock_transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.CASCADE,
        db_column="stock_transfer_id",
        related_name="items",
    )
    product_code = models.CharField(max_length=32, default="", blank=True)
    product_name = models.CharField(max_length=128, default="", blank=True)
    qty = models.FloatField(default=0)

    class Meta:
        db_table = "stock_transfer_items"


class StockAdjustment(models.Model):
    adjustment_no = models.CharField(max_length=64, unique=True)
    adjustment_date = models.DateField()
    location = models.CharField(max_length=128, default="", blank=True)
    remarks = models.CharField(max_length=255, default="", blank=True)
    created_by = models.CharField(max_length=64, default="Admin", blank=True)
    created_date = models.DateField()

    class Meta:
        db_table = "stock_adjustments"


class StockAdjustmentItem(models.Model):
    stock_adjustment = models.ForeignKey(
        StockAdjustment,
        on_delete=models.CASCADE,
        db_column="stock_adjustment_id",
        related_name="items",
    )
    product_code = models.CharField(max_length=32, default="", blank=True)
    product_name = models.CharField(max_length=128, default="", blank=True)
    old_qty = models.FloatField(default=0)
    adjustment_sign = models.CharField(max_length=1, default="-")
    adjustment_qty = models.FloatField(default=0)
    new_qty = models.FloatField(default=0)
    reason = models.CharField(max_length=64, default="Manual Correction")

    class Meta:
        db_table = "stock_adjustment_items"


class StockTake(models.Model):
    stock_take_no = models.CharField(max_length=64, unique=True)
    stock_take_date = models.DateField()
    location = models.CharField(max_length=128, default="", blank=True)
    status = models.CharField(max_length=32, default="Pending")
    remarks = models.CharField(max_length=255, default="", blank=True)
    user_name = models.CharField(max_length=64, default="Admin", blank=True)
    last_stock_take_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "stock_takes"


class StockTakeItem(models.Model):
    stock_take = models.ForeignKey(
        StockTake,
        on_delete=models.CASCADE,
        db_column="stock_take_id",
        related_name="items",
    )
    product_code = models.CharField(max_length=32, default="", blank=True)
    product_name = models.CharField(max_length=128, default="", blank=True)
    system_qty = models.FloatField(default=0)
    physical_qty = models.FloatField(default=0)
    variance = models.FloatField(default=0)

    class Meta:
        db_table = "stock_take_items"


class PurchasePayment(models.Model):
    payment_no = models.CharField(max_length=64, unique=True)
    payment_date = models.DateField()
    tran_no = models.CharField(max_length=64, default="", blank=True)
    supplier_invoice_no = models.CharField(max_length=64, default="", blank=True)
    supplier = models.CharField(max_length=128, default="", blank=True)
    amount = models.FloatField(default=0)
    mode = models.CharField(max_length=32, default="Cash")
    remarks = models.CharField(max_length=255, default="", blank=True)

    class Meta:
        db_table = "purchase_payments"

#####Customer#####
from django.db import models


class Customer(models.Model):

    customer_code = models.CharField(max_length=20, unique=True)
    customer_name = models.CharField(max_length=200)

    # Additional Tab
    address1 = models.CharField(max_length=200, blank=True, null=True)
    address2 = models.CharField(max_length=200, blank=True, null=True)
    address3 = models.CharField(max_length=200, blank=True, null=True)

    country = models.CharField(max_length=100, blank=True, null=True)
    postal = models.CharField(max_length=20, blank=True, null=True)

    phone_number = models.CharField(max_length=20, blank=True, null=True)
    hand_phone_number = models.CharField(max_length=20, blank=True, null=True)
    fax_no = models.CharField(max_length=20, blank=True, null=True)

    email = models.EmailField(blank=True, null=True)
    website = models.CharField(max_length=200, blank=True, null=True)

    company_reg_no = models.CharField(max_length=100, blank=True, null=True)

    tax = models.CharField(max_length=100, blank=True, null=True)
    price_group = models.CharField(max_length=100, blank=True, null=True)
    contact_type = models.CharField(max_length=100, blank=True, null=True)
    area = models.CharField(max_length=100, blank=True, null=True)
    currency = models.CharField(max_length=50, blank=True, null=True)
    terms = models.CharField(max_length=100, blank=True, null=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    remarks = models.TextField(blank=True, null=True)
    cheque_print_name = models.CharField(max_length=200, blank=True, null=True)

    is_active = models.BooleanField(default=True)

    created_by = models.CharField(max_length=100)

    def __str__(self):
        return self.customer_name
    
class CustomerLogin(models.Model):

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)

    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)

    is_active = models.BooleanField(default=True)

class CustomerContact(models.Model):

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)

    contact_person = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)

    phone_no = models.CharField(max_length=20, blank=True, null=True)
    handphone_no = models.CharField(max_length=20, blank=True, null=True)

    fax_no = models.CharField(max_length=20, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)

class CustomerShipping(models.Model):

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)

    delivery_name = models.CharField(max_length=200)

    delivery_address1 = models.CharField(max_length=200)
    delivery_address2 = models.CharField(max_length=200, blank=True, null=True)
    delivery_address3 = models.CharField(max_length=200, blank=True, null=True)

    phone_no = models.CharField(max_length=20, blank=True, null=True)
    handphone_no = models.CharField(max_length=20, blank=True, null=True)

    fax_no = models.CharField(max_length=20, blank=True, null=True)

    country = models.CharField(max_length=100)
    postal = models.CharField(max_length=20)

    email = models.EmailField(blank=True, null=True)

    attention = models.CharField(max_length=200, blank=True, null=True)

    default_load_invoice = models.BooleanField(default=False)

class CustomerSalesman(models.Model):

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)

    salesman_name = models.CharField(max_length=200)


class Supplier(models.Model):
    supplier_code = models.CharField(max_length=20, unique=True)
    supplier_name = models.CharField(max_length=200)

    # Additional Tab
    address1 = models.CharField(max_length=200, blank=True, null=True)
    address2 = models.CharField(max_length=200, blank=True, null=True)
    address3 = models.CharField(max_length=200, blank=True, null=True)

    country = models.CharField(max_length=100, blank=True, null=True)
    postal = models.CharField(max_length=20, blank=True, null=True)

    phone_number = models.CharField(max_length=20, blank=True, null=True)
    hand_phone_number = models.CharField(max_length=20, blank=True, null=True)
    fax_no = models.CharField(max_length=20, blank=True, null=True)

    email = models.EmailField(blank=True, null=True)
    website = models.CharField(max_length=200, blank=True, null=True)

    company_reg_no = models.CharField(max_length=100, blank=True, null=True)

    tax = models.CharField(max_length=100, blank=True, null=True)
    price_group = models.CharField(max_length=100, blank=True, null=True)
    contact_type = models.CharField(max_length=100, blank=True, null=True)
    area = models.CharField(max_length=100, blank=True, null=True)
    currency = models.CharField(max_length=50, blank=True, null=True)
    terms = models.CharField(max_length=100, blank=True, null=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    remarks = models.TextField(blank=True, null=True)
    cheque_print_name = models.CharField(max_length=200, blank=True, null=True)

    is_active = models.BooleanField(default=True)

    created_by = models.CharField(max_length=100)

    def __str__(self):
        return self.supplier_name


class SupplierLogin(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)

    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)

    is_active = models.BooleanField(default=True)


class SupplierContact(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)

    contact_person = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)

    phone_no = models.CharField(max_length=20, blank=True, null=True)
    handphone_no = models.CharField(max_length=20, blank=True, null=True)

    fax_no = models.CharField(max_length=20, blank=True, null=True)


class TaxMaster(models.Model):
    tax_name = models.CharField(max_length=200, unique=True)
    tax_type = models.CharField(max_length=100, blank=True, null=True)
    tax_code = models.CharField(max_length=100, blank=True, null=True)
    tax_for = models.CharField(max_length=50, default="Both")
    tax_percentage = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    sort_code = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_by = models.CharField(max_length=100)
    created_date = models.DateField(auto_now_add=True)

    class Meta:
        db_table = "tax_master"

    def __str__(self):
        return self.tax_name


class TermsMaster(models.Model):
    term_name = models.CharField(max_length=200, unique=True)
    no_of_days = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.CharField(max_length=100)
    created_date = models.DateField(auto_now_add=True)

    class Meta:
        db_table = "terms_master"

    def __str__(self):
        return self.term_name


class CurrencyMaster(models.Model):
    currency_code = models.CharField(max_length=20, unique=True)
    currency_name = models.CharField(max_length=200)
    currency_rate = models.DecimalField(max_digits=12, decimal_places=4, default=1)
    is_active = models.BooleanField(default=True)
    created_by = models.CharField(max_length=100)
    created_date = models.DateField(auto_now_add=True)

    class Meta:
        db_table = "currency_master"

    def __str__(self):
        return self.currency_name


# class Customer(models.Model):
#     customer_code = models.CharField(max_length=20, unique=True)
#     customer_name = models.CharField(max_length=200)
#     address = models.TextField(blank=True, null=True)
#     phone_no = models.CharField(max_length=20, blank=True, null=True)
#     email = models.EmailField(blank=True, null=True)
#     created_by = models.CharField(max_length=100)

#     def __str__(self):
#         return self.customer_name
