import random
from datetime import date, timedelta

from django.db import connection, transaction

from .models import (
    DebitNote,
    GoodsReceipt,
    GoodsReceiptItem,
    GoodsReturn,
    GoodsReturnItem,
    Inventory,
    Product,
    PurchaseInvoiceEntry,
    PurchaseInvoiceEntryItem,
    PurchasePayment,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseProduct,
    SalesInvoice,
    SalesOrder,
    SalesOrderItem,
    StockAdjustment,
    StockAdjustmentItem,
    StockRequest,
    StockRequestItem,
    StockTake,
    StockTakeItem,
    StockTransfer,
    StockTransferItem,
    SupplierLedgerEntry,
    SupplierMaster,
    WarehouseMaster,
)


def _table_column_names(table_name):
    with connection.cursor() as cursor:
        cursor.execute(f"PRAGMA table_info('{table_name}')")
        rows = cursor.fetchall()
    return {row[1] for row in rows}


def ensure_schema():
    existing = set(connection.introspection.table_names())
    models_in_order = [
        PurchaseOrder,
        SalesOrder,
        PurchaseInvoice,
        SalesInvoice,
        Product,
        Inventory,
        SalesOrderItem,
        SupplierMaster,
        WarehouseMaster,
        PurchaseProduct,
        PurchaseOrderItem,
        GoodsReceipt,
        GoodsReceiptItem,
        GoodsReturn,
        GoodsReturnItem,
        DebitNote,
        SupplierLedgerEntry,
        PurchaseInvoiceEntry,
        PurchaseInvoiceEntryItem,
        PurchasePayment,
        StockRequest,
        StockRequestItem,
        StockTransfer,
        StockTransferItem,
        StockAdjustment,
        StockAdjustmentItem,
        StockTake,
        StockTakeItem,
    ]
    with connection.schema_editor() as schema_editor:
        for model in models_in_order:
            if model._meta.db_table not in existing:
                schema_editor.create_model(model)
                existing.add(model._meta.db_table)

        # Lightweight schema evolution for non-migration setup.
        if PurchaseOrder._meta.db_table in existing:
            existing_cols = _table_column_names(PurchaseOrder._meta.db_table)
            for field in PurchaseOrder._meta.local_fields:
                if field.column in existing_cols:
                    continue
                if field.auto_created or not field.concrete:
                    continue
                schema_editor.add_field(PurchaseOrder, field)


def seed_purchase_masters():
    if not SupplierMaster.objects.exists():
        SupplierMaster.objects.bulk_create(
            [
                SupplierMaster(
                    code="SUP-001",
                    name="Radha Export Pvt",
                    contact="Sai Kumar",
                    address="12 Mount Road, Chennai",
                    country="India",
                    currency="INR",
                    payment_terms="Net 30",
                ),
                SupplierMaster(
                    code="SUP-002",
                    name="ABC Supplies",
                    contact="Ravi Prakash",
                    address="88 MG Road, Bengaluru",
                    country="India",
                    currency="INR",
                    payment_terms="Cash",
                ),
                SupplierMaster(
                    code="SUP-003",
                    name="Sai Traders",
                    contact="Kumaravel",
                    address="21 Ring Road, Hyderabad",
                    country="India",
                    currency="INR",
                    payment_terms="Credit",
                ),
            ]
        )

    if not WarehouseMaster.objects.exists():
        WarehouseMaster.objects.bulk_create(
            [
                WarehouseMaster(name="Chennai Main"),
                WarehouseMaster(name="Bangalore Central"),
                WarehouseMaster(name="Hyderabad Depot"),
            ]
        )

    if not PurchaseProduct.objects.exists():
        PurchaseProduct.objects.bulk_create(
            [
                PurchaseProduct(
                    code="PRD-001",
                    name="Dove Shampoo",
                    description="Dove Shampoo 650ml bottle",
                    unit_price=30.0,
                    tax_percent=5.0,
                ),
                PurchaseProduct(
                    code="PRD-002",
                    name="Notebook Pack",
                    description="A4 ruled notebook pack",
                    unit_price=50.0,
                    tax_percent=9.0,
                ),
                PurchaseProduct(
                    code="PRD-003",
                    name="Printer Paper",
                    description="A4 copier paper 500 sheets",
                    unit_price=240.0,
                    tax_percent=12.0,
                ),
            ]
        )


def seed_data():
    seed_purchase_masters()

    if SalesOrder.objects.exists():
        return

    random.seed(42)
    suppliers = ["Royal Fabric", "Metro Stitch", "Fine Cotton", "Premium Threads"]
    customers = ["Customer A", "Customer B", "Customer C", "Customer D", "CASH"]
    salesmen = ["Arun", "Maya", "Ravi", "Nisha"]

    product_seed = [
        ("Formal Shirt", "Shirts", "Formal", 450, 850, 90, 20),
        ("Casual Shirt", "Shirts", "Casual", 380, 760, 120, 25),
        ("Denim Pant", "Pants", "Denim", 520, 980, 75, 18),
        ("Cotton Pant", "Pants", "Cotton", 460, 920, 65, 18),
        ("Leather Belt", "Accessories", "Belts", 180, 420, 40, 15),
        ("Tie", "Accessories", "Ties", 90, 240, 55, 15),
        ("Kurta", "Ethnic", "Men Ethnic", 500, 1100, 45, 12),
        ("Jacket", "Outerwear", "Winter", 900, 1800, 30, 10),
    ]
    Product.objects.bulk_create(
        [
            Product(
                product_name=name,
                department=department,
                category=category,
                cost_price=cost,
                sell_price=sell,
                stock_qty=stock,
                reorder_qty=reorder,
            )
            for name, department, category, cost, sell, stock, reorder in product_seed
        ]
    )
    products = list(Product.objects.all().values("id", "sell_price"))
    today = date.today()

    with transaction.atomic():
        for day_offset in range(120):
            d = today - timedelta(days=119 - day_offset)

            sales_count = random.randint(1, 3) if d.weekday() < 6 else random.randint(0, 1)
            for i in range(sales_count):
                amount = random.randint(1200, 16000)
                invoice_no = f"SI{d.strftime('%Y%m%d')}{i + 1:02d}"
                order_no = f"SO-{d.strftime('%m%d')}-{i + 1:02d}"
                customer = random.choice(customers)
                paid = round(amount * random.uniform(0.55, 1.0), 2)
                salesman = random.choice(salesmen)

                sales_order = SalesOrder.objects.create(
                    order_no=order_no,
                    order_date=d,
                    invoice_no=invoice_no,
                    customer=customer,
                    amount=amount,
                    paid_amount=paid,
                    salesman=salesman,
                )
                SalesInvoice.objects.create(
                    invoice_no=invoice_no,
                    invoice_date=d,
                    customer=customer,
                    total_amount=amount,
                    paid_amount=paid,
                )

                for _ in range(random.randint(1, 3)):
                    p = random.choice(products)
                    qty = random.randint(1, 5)
                    item_amount = round(qty * p["sell_price"], 2)
                    SalesOrderItem.objects.create(
                        sales_order_id=sales_order.id,
                        product_id=p["id"],
                        qty=qty,
                        amount=item_amount,
                    )

            purchase_count = random.randint(0, 2)
            for i in range(purchase_count):
                amount = random.randint(900, 14000)
                invoice_no = f"PI{d.strftime('%Y%m%d')}{i + 1:02d}"
                order_no = f"PO-{d.strftime('%m%d')}-{i + 1:02d}"
                supplier = random.choice(suppliers)
                paid = round(amount * random.uniform(0.5, 1.0), 2)

                PurchaseOrder.objects.create(
                    order_no=order_no,
                    order_date=d,
                    invoice_no=invoice_no,
                    supplier=supplier,
                    amount=amount,
                    paid_amount=paid,
                    status="Closed" if paid >= amount else "Approved",
                )
                PurchaseInvoice.objects.create(
                    invoice_no=invoice_no,
                    invoice_date=d,
                    supplier=supplier,
                    total_amount=amount,
                    paid_amount=paid,
                )


def init_db():
    ensure_schema()
    seed_data()
