from django.shortcuts import render

# Create your views here.
import json
from datetime import date

from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import SalesQuotation, SalesQuotationItem
from .models import SalesOrder, SalesOrderItem
from .models import Delivery

from django.db.models import Sum, Q
from .models import Inventory, GoodsReceiptItem, SalesOrderItem, Product, SupplierMaster

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib import styles
from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io

from .db import init_db
from .models import (
    DebitNote,
    GoodsReceipt,
    GoodsReceiptItem,
    GoodsReturn,
    GoodsReturnItem,
    Inventory,
    PurchaseInvoice,
    PurchaseInvoiceEntry,
    PurchaseInvoiceEntryItem,
    PurchasePayment,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseProduct,
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
    TaxModuleSetting,
    WarehouseMaster,
)
from .services.dashboard import dashboard_data

PO_PAYMENT_TERMS = ["Net 30", "Cash", "Credit"]
TAX_MODULE_OPTIONS = [
    {"key": "purchase", "label": "Purchase"},
    {"key": "purchase_order", "label": "Purchase Order"},
    {"key": "goods_receipt", "label": "Goods Receipt"},
    {"key": "goods_return", "label": "Goods Return"},
    {"key": "purchase_invoice", "label": "Purchase Invoice"},
    {"key": "sales", "label": "Sales"},
    {"key": "sales_quotation", "label": "Sales Quotation"},
    {"key": "sales_orders", "label": "Sales Orders"},
    {"key": "delivery", "label": "Delivery"},
    {"key": "sales_return", "label": "Sales Return"},
    {"key": "invoice", "label": "Invoice"},
    {"key": "stock", "label": "Stock"},
    {"key": "stock_request", "label": "Stock Request"},
    {"key": "stock_transfer", "label": "Stock Transfer"},
    {"key": "stock_adjustment", "label": "Stock Adjustment"},
    {"key": "stock_take", "label": "Stock Take"},
    {"key": "finance", "label": "Finance"},
]


def _module_tax_percent(module_key, default=0.0):
    setting = (
        TaxModuleSetting.objects.filter(module_key=module_key)
        .values("tax_percent")
        .first()
    )
    if setting:
        return _to_float(setting.get("tax_percent"), default)
    return _to_float(default, 0)


def _effective_purchase_tax_percent():
    purchase_tax = _module_tax_percent("purchase", 0)
    purchase_order_tax = _module_tax_percent("purchase_order", 0)
    if purchase_tax <= 0 and purchase_order_tax > 0:
        return purchase_order_tax
    return purchase_tax


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _next_doc_number(prefix, existing_values):
    max_no = 100
    for value in existing_values:
        text = (value or "").strip()
        if not text.startswith(prefix):
            continue
        suffix = text[len(prefix) :]
        if suffix.isdigit():
            max_no = max(max_no, int(suffix))
    return f"{prefix}{max_no + 1}"


def _to_iso_or_today(value):
    text = (value or "").strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    return date.today().isoformat()


def _make_product_code(name):
    text = (name or "").upper()
    clean = "".join(ch if ch.isalnum() else "-" for ch in text)
    while "--" in clean:
        clean = clean.replace("--", "-")
    clean = clean.strip("-")
    return f"STK-{clean[:18] or 'ITEM'}"


def _transaction_product_options():
    options = []
    seen = set()

    po_rows = (
        PurchaseOrderItem.objects.exclude(product_name__exact="")
        .values("product_code", "product_name")
        .distinct()
        .order_by("product_name")
    )
    for row in po_rows:
        name = (row.get("product_name") or "").strip()
        if not name:
            continue
        code = (row.get("product_code") or "").strip() or _make_product_code(name)
        key = f"{code}|{name}".lower()
        if key in seen:
            continue
        seen.add(key)
        options.append({"code": code, "name": name})

    if not options:
        fallback_rows = (
            PurchaseProduct.objects.exclude(name__exact="")
            .values("code", "name")
            .order_by("name")
        )
        for row in fallback_rows:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            code = (row.get("code") or "").strip() or _make_product_code(name)
            key = f"{code}|{name}".lower()
            if key in seen:
                continue
            seen.add(key)
            options.append({"code": code, "name": name})
    return options


def _inventory_stock_map():
    stock_by_location = {}
    for inv in Inventory.objects.all():
        loc = (inv.location or "").strip()
        pcode = (inv.product_code or "").strip()
        if not loc or not pcode:
            continue
        key = f"{loc}|{pcode}"
        stock_by_location[key] = stock_by_location.get(key, 0) + _to_float(inv.stock_qty, 0)
    return stock_by_location


def _stock_locations():
    locations = list(WarehouseMaster.objects.order_by("name").values_list("name", flat=True))
    if locations:
        return locations
    return ["Warehouse", "Store A", "Store B", "Store C"]


def render_page(
    request,
    template_name,
    page_title,
    active_page,
    inventory_open=False,
    sales_open=False,
    purchase_open=False,
    purchase_section=False,
    stock_open=False,
    stock_section=False,
    extra=None,
):
    context = {
        "page_title": page_title,
        "active_page": active_page,
        "inventory_open": inventory_open,
        "purchase_open": purchase_open,
        "purchase_section": purchase_section,
        "stock_open": stock_open,
        "stock_section": stock_section,
    }
    if extra:
        context.update(extra)
    return render(request, template_name, context)


@login_required
def dashboard_view(request):
    return render(request, "dashboard.html")


def inventory_view(request):
    return render_page(request, "inventory.html", "Inventory", "inventory", inventory_open=True)


def master_view(request):
    return render_page(request, "master.html", "Master", "master", inventory_open=True)


def product_view(request):
    return render_page(request, "product.html", "Product", "product", inventory_open=True)


def purchase_view(request):
    return render_page(
        request,
        "purchase.html",
        "Purchase",
        "purchase",
        inventory_open=True,
        purchase_open=True,
        purchase_section=True,
    )


def purchase_order_view(request):
    init_db()
    purchase_tax_percent = _effective_purchase_tax_percent()
    suppliers = list(
        SupplierMaster.objects.order_by("name").values(
            "code", "name", "contact", "address", "country", "currency", "payment_terms"
        )
    )
    products = list(
        PurchaseProduct.objects.order_by("name").values(
            "code", "name", "description", "unit_price", "tax_percent"
        )
    )
    warehouses = list(WarehouseMaster.objects.order_by("name").values_list("name", flat=True))
    po_rows = []
    for po in PurchaseOrder.objects.order_by("-order_date", "-id")[:120]:
        first_item = po.po_items.order_by("id").first()
        row_tax_percent = purchase_tax_percent if first_item else ""
        po_rows.append(
            {
                "po_no": po.order_no,
                "item": first_item.product_name if first_item else "",
                "qty": first_item.qty if first_item else "",
                "supplier_name": po.supplier,
                "unit_price": first_item.unit_price if first_item else "",
                "tax_percent": row_tax_percent,
                "net_total": first_item.net_total if first_item else po.amount,
                "status": po.status or "Draft",
                "warehouse": po.warehouse or "",
                "po_date": po.order_date.strftime("%Y-%m-%d"),
            }
        )

    return render_page(
        request,
        "purchase_order.html",
        "Purchase Order",
        "purchase_order",
        inventory_open=True,
        purchase_open=True,
        purchase_section=True,
        extra={
            "po_suppliers": suppliers,
            "po_products": products,
            "po_warehouses": warehouses,
            "po_payment_terms": PO_PAYMENT_TERMS,
            "po_today": date.today().isoformat(),
            "po_rows": po_rows,
            "purchase_tax_percent": purchase_tax_percent,
        },
    )


def goods_receipt_view(request):
    init_db()
    warehouses = list(WarehouseMaster.objects.order_by("name").values_list("name", flat=True))
    suppliers = list(
        SupplierMaster.objects.order_by("name").values("code", "name")
    )
    approved_pos = []
    for po in PurchaseOrder.objects.filter(status__in=["Approved", "Partially Received"]).order_by("-order_date", "-id")[:200]:
        approved_pos.append(
            {
                "po_no": po.order_no,
                "supplier": po.supplier,
                "supplier_code": po.supplier_code or "",
                "warehouse": po.warehouse or "",
                "order_date": po.order_date.strftime("%Y-%m-%d"),
            }
        )

    gr_rows = []
    for gr in GoodsReceipt.objects.order_by("-receipt_date", "-id")[:200]:
        subtotal = 0.0
        tax_total = 0.0
        for item in gr.items.all():
            subtotal += item.line_total
            tax_total += max(item.net_total - item.line_total, 0)
        gr_rows.append(
            {
                "gr_no": gr.gr_no,
                "tran_date": gr.receipt_date.strftime("%Y-%m-%d"),
                "supplier": gr.supplier,
                "status": gr.status,
                "invoice_no": gr.invoice_no,
                "sub_total": subtotal,
                "tax": tax_total,
                "net_total": subtotal + tax_total,
            }
        )

    return render_page(
        request,
        "goods_receipt.html",
        "Goods Receipt",
        "goods_receipt",
        inventory_open=True,
        purchase_open=True,
        purchase_section=True,
        extra={
            "gr_today": date.today().isoformat(),
            "gr_warehouses": warehouses,
            "gr_suppliers": suppliers,
            "gr_approved_pos": approved_pos,
            "gr_rows": gr_rows,
        },
    )


def goods_return_view(request):
    init_db()
    suppliers = list(SupplierMaster.objects.order_by("name").values("code", "name"))
    warehouses = list(WarehouseMaster.objects.order_by("name").values_list("name", flat=True))

    gr_candidates = []
    for gr in GoodsReceipt.objects.order_by("-receipt_date", "-id")[:250]:
        gr_candidates.append(
            {
                "gr_no": gr.gr_no,
                "supplier": gr.supplier,
                "invoice_no": gr.invoice_no,
                "location": gr.location or "",
                "receipt_date": gr.receipt_date.strftime("%Y-%m-%d"),
            }
        )

    return_rows = []
    for ret in GoodsReturn.objects.order_by("-return_date", "-id")[:250]:
        subtotal = 0.0
        tax_total = 0.0
        for item in ret.items.all():
            subtotal += _to_float(item.line_total, 0)
            tax_total += max(_to_float(item.net_total, 0) - _to_float(item.line_total, 0), 0)
        return_rows.append(
            {
                "return_no": ret.return_no,
                "tran_date": ret.return_date.strftime("%Y-%m-%d"),
                "supplier": ret.supplier,
                "status": ret.status,
                "invoice_no": ret.invoice_no,
                "location": ret.location or "",
                "sub_total": subtotal,
                "tax": tax_total,
                "net_total": subtotal + tax_total,
            }
        )

    return render_page(
        request,
        "goods_return.html",
        "Goods Return",
        "goods_return",
        inventory_open=True,
        purchase_open=True,
        purchase_section=True,
        extra={
            "gor_today": date.today().isoformat(),
            "gor_suppliers": suppliers,
            "gor_warehouses": warehouses,
            "gor_receipts": gr_candidates,
            "gor_rows": return_rows,
        },
    )


def purchase_invoice_view(request):
    init_db()
    suppliers = list(SupplierMaster.objects.order_by("name").values("code", "name"))
    warehouses = list(WarehouseMaster.objects.order_by("name").values_list("name", flat=True))
    receipts = []
    for gr in GoodsReceipt.objects.order_by("-receipt_date", "-id")[:250]:
        receipts.append(
            {
                "gr_no": gr.gr_no,
                "supplier": gr.supplier,
                "invoice_no": gr.invoice_no,
                "location": gr.location or "",
                "receipt_date": gr.receipt_date.strftime("%Y-%m-%d"),
                "po_no": gr.purchase_order.order_no if gr.purchase_order_id else "",
            }
        )

    rows = []
    for inv in PurchaseInvoiceEntry.objects.order_by("-invoice_date", "-id")[:250]:
        rows.append(
            {
                "tran_no": inv.tran_no,
                "tran_date": inv.invoice_date.strftime("%Y-%m-%d"),
                "supplier": inv.supplier,
                "invoice_no": inv.supplier_invoice_no,
                "sub_total": _to_float(inv.sub_total, 0),
                "tax": _to_float(inv.tax_total, 0),
                "net_total": _to_float(inv.net_total, 0),
                "paid_amount": _to_float(inv.paid_amount, 0),
                "balance_amount": _to_float(inv.balance_amount, 0),
                "status": inv.status,
                "payment_status": inv.payment_status,
                "location": inv.location or "",
            }
        )

    return render_page(
        request,
        "purchase_invoice.html",
        "Purchase Invoice",
        "purchase_invoice",
        inventory_open=True,
        purchase_open=True,
        purchase_section=True,
        extra={
            "pi_today": date.today().isoformat(),
            "pi_suppliers": suppliers,
            "pi_warehouses": warehouses,
            "pi_receipts": receipts,
            "pi_rows": rows,
        },
    )


def sales_view(request):
    return render_page(request, "sales.html", "Sales", "sales", inventory_open=True)


def sales_quotation_view(request):
    
    status = request.GET.get("status")
    customer = request.GET.get("customer")

    quotations = SalesQuotation.objects.all().order_by("-id")

    if status == "approved":
        quotations = quotations.filter(approved=True)

    elif status == "unapproved":
        quotations = quotations.filter(approved=False)
        
    # Filter by customer (partial match)
    if customer:
        quotations = quotations.filter(customer_name__icontains=customer)

    return render_page(
        request,
        "sales_quotation.html",
        "Sales Quotation",
        "sales_quotation",
        inventory_open=True,
        sales_open=True,
        extra={
            "quotations": quotations,
            "current_status": status
        }
    )



def salesquotation_print(request):
    
    customer = request.GET.get("customer")
    status = request.GET.get("status")

    quotations = SalesQuotation.objects.all()

    if customer:
        quotations = quotations.filter(customer_name__icontains=customer)

    if status:
        if status == "approved":
            quotations = quotations.filter(approved=True)
        elif status == "unapproved":
            quotations = quotations.filter(approved=False)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    elements = []
    
    styles = getSampleStyleSheet()

    heading_style = styles["Heading1"]
    heading = Paragraph("Sales Quotation", heading_style)

    elements.append(heading)
    elements.append(Spacer(1, 0.3 * inch))

    data = [[ "Customer", "Approved", "Net Total"]]

    for q in quotations:
        data.append([
            q.customer_name,
            "Approved" if q.approved else "Unapproved",
            str(q.total_amount)
        ])

    table = Table(data)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
    ]))

    elements.append(table)
    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=sales_quotations.pdf"

    return response


def delivery_view(request):
    
    if request.method == "POST":

        action_type = request.POST.get("action_type")
        select_all = request.POST.get("select_all")
        selected_ids = request.POST.getlist("selected_ids")

        if select_all == "yes":
            deliveries = Delivery.objects.all()
        else:
            deliveries = Delivery.objects.filter(id__in=selected_ids)

        if request.method == "POST":
    
            action_type = request.POST.get("action_type")
            selected_ids = request.POST.getlist("selected_ids")

            if action_type == "delete":

                if selected_ids:
                    Delivery.objects.filter(id__in=selected_ids).delete()
                else:
                    Delivery.objects.all().delete()

                return redirect("delivery")

        # PRINT
        elif action_type == "print":
            for d in deliveries:
                print(d.tran_no)  # later connect to PDF

        return redirect("delivery")

    deliveries = Delivery.objects.all().order_by("-id")

    return render_page(
        request,
        "delivery.html",
        "Delivery Management",
        "delivery",
        extra={"deliveries": deliveries}
    )
    
def delivery_print_view(request):
    
    ids = request.GET.get("ids")

    if ids:
        id_list = ids.split(",")
        deliveries = Delivery.objects.filter(id__in=id_list)
    else:
        deliveries = Delivery.objects.all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    elements = []
    styles = getSampleStyleSheet()

    title = Paragraph("<b>Sales Delivery Report</b>", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 0.3 * inch))

    # Table Data
    data = [
        ["Tran No", "Date", "Customer", "Status", "Net Total"]
    ]

    for d in deliveries:
        data.append([
            d.tran_no,
            str(d.tran_date),
            d.customer,
            d.status,
            str(d.net_total)
        ])

    table = Table(data, repeatRows=1)

    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('ALIGN', (4,1), (-1,-1), 'RIGHT'),
    ]))

    elements.append(table)

    doc.build(elements)

    buffer.seek(0)

    return HttpResponse(
        buffer,
        content_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="delivery_report.pdf"'}
    )
    
    
def delivery_new_view(request):
    
    if request.method == "POST":

        tran_date = request.POST.get("tran_date")
        if not tran_date:
            tran_date = datetime.today().strftime("%Y-%m-%d")

        # Simple auto number
        count = Delivery.objects.count() + 1
        tran_no = f"DO-{count:04d}"

        delivery = Delivery.objects.create(
            tran_no=tran_no,
            tran_date=tran_date,
            customer=request.POST.get("customer_name"),
            sub_total=0,
            tax=0,
            net_total=0,
        )

        product_names = request.POST.getlist("product_name[]")
        qtys = request.POST.getlist("qty[]")
        prices = request.POST.getlist("price[]")

        sub_total = 0

        for i in range(len(product_names)):
            if product_names[i]:

                qty = float(qtys[i] or 0)
                price = float(prices[i] or 0)
                total = qty * price

                sub_total += total

                DeliveryItem.objects.create(
                    delivery=delivery,
                    product_name=product_names[i],
                    qty=qty,
                    price=price,
                    total=total
                )

        delivery.sub_total = sub_total
        delivery.net_total = sub_total
        delivery.save()

        return redirect("delivery")

    return render_page(
        request,
        "delivery_new.html",
        "Delivery - New",
        "delivery"
    )
def sales_return_view(request):
    return render_page(
        request,
        "sales_return.html",
        "Sales Return",
        "sales_return",
        inventory_open=True,
        sales_open=True,
    )
    
def invoice_view(request):
    return render_page(
        request,
        "invoice.html",
        "Invoice",
        "invoice",
        inventory_open=True,
        sales_open=True,
    )  

def salesquotation_new_view(request):
    
    if request.method == "POST":
        tran_no = request.POST.get("tran_no")
        tran_date = request.POST.get("tran_date")
        customer_name = request.POST.get("customer_name")
        remarks = request.POST.get("remarks")

        # Get approved status from button
        status = request.POST.get("status")
        is_approved = True if status == "approved" else False

        # Create quotation
        quotation = SalesQuotation.objects.create(
            tran_no=tran_no,
            tran_date=tran_date,
            customer_name=customer_name,
            remarks=remarks,
            approved=is_approved,
        )

        product_codes = request.POST.getlist("product_code[]")
        product_names = request.POST.getlist("product_name[]")
        qtys = request.POST.getlist("qty[]")
        prices = request.POST.getlist("price[]")
        totals = request.POST.getlist("total[]")

        total_amount = 0

        for i in range(len(product_codes)):
            if product_codes[i]:  # avoid empty row
                SalesQuotationItem.objects.create(
                    quotation=quotation,
                    product_code=product_codes[i],
                    product_name=product_names[i],
                    qty=float(qtys[i] or 0),
                    price=float(prices[i] or 0),
                    total=float(totals[i] or 0),
                )
                total_amount += float(totals[i] or 0)

        quotation.total_amount = total_amount
        quotation.save()

        return redirect("sales_quotation")

    return render_page(
        request,
        "salesquotation_new.html",
        "Add/Edit Sales Quotation",
        "sales_quotation",
        inventory_open=True,
        sales_open=True,
    )

def salesquotation_new_view(request):
    
    if request.method == "POST":
        tran_no = request.POST.get("tran_no")
        tran_date = request.POST.get("tran_date")
        customer_name = request.POST.get("customer_name")
        remarks = request.POST.get("remarks")

        # Get approved status from button
        status = request.POST.get("status")
        is_approved = True if status == "approved" else False

        # Create quotation
        quotation = SalesQuotation.objects.create(
            tran_no=tran_no,
            tran_date=tran_date,
            customer_name=customer_name,
            remarks=remarks,
            approved=is_approved,
        )

        product_codes = request.POST.getlist("product_code[]")
        product_names = request.POST.getlist("product_name[]")
        qtys = request.POST.getlist("qty[]")
        prices = request.POST.getlist("price[]")
        totals = request.POST.getlist("total[]")

        total_amount = 0

        for i in range(len(product_codes)):
            if product_codes[i]:  # avoid empty row
                SalesQuotationItem.objects.create(
                    quotation=quotation,
                    product_code=product_codes[i],
                    product_name=product_names[i],
                    qty=float(qtys[i] or 0),
                    price=float(prices[i] or 0),
                    total=float(totals[i] or 0),
                )
                total_amount += float(totals[i] or 0)

        quotation.total_amount = total_amount
        quotation.save()

        return redirect("sales_quotation")

    return render_page(
        request,
        "salesquotation_new.html",
        "Add/Edit Sales Quotation",
        "sales_quotation",
        inventory_open=True,
        sales_open=True,
    )

def salesquotation_print(request):
    
    customer = request.GET.get("customer")
    status = request.GET.get("status")

    quotations = SalesQuotation.objects.all()

    if customer:
        quotations = quotations.filter(customer_name__icontains=customer)

    if status:
        if status == "approved":
            quotations = quotations.filter(approved=True)
        elif status == "unapproved":
            quotations = quotations.filter(approved=False)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    elements = []
    
    styles = getSampleStyleSheet()

    heading_style = styles["Heading1"]
    heading = Paragraph("Sales Quotation", heading_style)

    elements.append(heading)
    elements.append(Spacer(1, 0.3 * inch))

    data = [[ "Customer", "Approved", "Net Total"]]

    for q in quotations:
        data.append([
            q.customer_name,
            "Approved" if q.approved else "Unapproved",
            str(q.total_amount)
        ])

    table = Table(data)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
    ]))

    elements.append(table)
    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=sales_quotations.pdf"

    return response

def salesquotation_delete(request):
    
    if request.method == "POST":
        ids = request.POST.getlist("selected_ids")

        if ids:
            SalesQuotation.objects.filter(id__in=ids).delete()

    return redirect("sales_quotation")  

def sales_orders_view(request):
    
   
    customer = request.GET.get("customer")
    printed = request.GET.get("printed")   # NEW

    orders = SalesOrder.objects.all().order_by("-id")

   

    if customer:
        orders = orders.filter(customer__icontains=customer)

    # NEW PRINT FILTER
    if printed == "true":
        orders = orders.filter(printed=True)
    elif printed == "false":
        orders = orders.filter(printed=False)

    return render_page(
        request,
        "sales_orders.html",
        "Sales Orders",
        "sales_orders",
        inventory_open=True,
        sales_open=True,
        extra={
            "orders": orders,
            "current_customer": customer,
            "current_printed": printed
        }
    )
    

from datetime import datetime


def salesorders_new_view(request):
    
    if request.method == "POST":

        # 1️⃣ Get date
        tran_date = request.POST.get("tran_date")

        if not tran_date:
            tran_date = datetime.today().strftime("%Y-%m-%d")

        # Convert string to datetime object
        date_obj = datetime.strptime(tran_date, "%Y-%m-%d")

        # 2️⃣ Generate Auto Order Number
        month_year = date_obj.strftime("%m%y")
        prefix = f"SO-{month_year}-"

        count = SalesOrder.objects.filter(
            order_date__month=date_obj.month,
            order_date__year=date_obj.year
        ).count() + 1

        order_number = f"{prefix}{count:02d}"

        # 3️⃣ Create Order (CHANGED HERE)
        order = SalesOrder.objects.create(
            order_no=order_number,   # ✅ AUTO GENERATED
            order_date=tran_date,
            invoice_no="",
            customer=request.POST.get("customer_name"),
            amount=0,
            paid_amount=0,
            salesman=request.POST.get("salesman_code") or "Salesman 1"
        )

        product_codes = request.POST.getlist("product_code[]")
        product_names = request.POST.getlist("product_name[]")
        qtys = request.POST.getlist("qty[]")
        prices = request.POST.getlist("price[]")

        total_amount = 0

        for i in range(len(product_codes)):
            if product_codes[i]:

                qty = float(qtys[i] or 0)
                price = float(prices[i] or 0)
                amount = qty * price
                total_amount += amount

                SalesOrderItem.objects.create(
                    sales_order=order,
                    product_id=1,
                    qty=qty,
                    amount=amount
                )

        order.amount = total_amount
        order.save()

        return redirect("sales_orders")

    return render_page(
        request,
        "salesorders_new.html",
        "Sales Order - New",
        "sales_orders"
    )
    
def sales_orders_print(request):
    
    selected_ids = request.POST.getlist("selected_ids")

    # If rows selected → filter
    if selected_ids:
        orders = SalesOrder.objects.filter(id__in=selected_ids)
    else:
        # If none selected → print all
        orders = SalesOrder.objects.all()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="sales_orders.pdf"'

    doc = SimpleDocTemplate(response)
    elements = []

    data = [["Order No", "Date", "Customer", "Status", "Amount"]]

    for o in orders:
        data.append([
            o.order_no,
            str(o.order_date),
            o.customer,
            o.get_status_display(),
            str(o.amount)
        ])

    table = Table(data)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))

    elements.append(table)
    doc.build(elements)

    return response


def sales_orders_delete(request):
    
    if request.method == "POST":
        ids = request.POST.getlist("selected_ids")

        if ids:
            SalesOrder.objects.filter(id__in=ids).delete()

    return redirect("sales_orders")


def delivery_new_view(request):
    return render_page(
        request,
        "delivery_new.html",
        "Delivery - New",     
        "delivery"           
    )
    
def salesreturn_new_view(request):
    return render_page(
        request,
        "salesreturn_new.html",
        "Sales Return - New",     
        "sales_return"           
    )
    
def invoice_new_view(request):
    return render_page(
        request,
        "invoice_new.html",
        "Invoice - New",     
        "invoice"           
    )

def stock_view(request):
    return render_page(
        request,
        "stock.html",
        "Stock",
        "stock",
        inventory_open=True,
        stock_open=True,
        stock_section=True,
    )


def stock_request_view(request):
    init_db()
    rows = []
    for sr in StockRequest.objects.order_by("-request_date", "-id")[:250]:
        rows.append(
            {
                "stock_req_no": sr.request_no,
                "from_location": sr.from_location or "",
                "to_location": sr.to_location or "",
                "status": sr.status or "Draft",
                "stock_req_date": sr.request_date.strftime("%d/%m/%Y"),
                "create_date": sr.created_date.strftime("%d/%m/%Y"),
                "remarks": sr.remarks or "",
            }
        )
    return render_page(
        request,
        "stock_request.html",
        "Stock Request",
        "stock_request",
        inventory_open=True,
        stock_open=True,
        stock_section=True,
        extra={
            "sr_today": date.today().isoformat(),
            "sr_rows": rows,
            "sr_locations": _stock_locations(),
        },
    )


def stock_request_new_view(request):
    init_db()
    existing = list(StockRequest.objects.values_list("request_no", flat=True))
    next_no = _next_doc_number("SR-", existing)
    sr_products = _transaction_product_options()
    stock_by_location = _inventory_stock_map()

    return render_page(
        request,
        "stock_request_form.html",
        "Add/Edit Stock Request",
        "stock_request",
        inventory_open=True,
        stock_open=True,
        stock_section=True,
        extra={
            "sr_today": date.today().isoformat(),
            "sr_next_no": next_no,
            "sr_locations": _stock_locations(),
            "sr_products": sr_products,
            "sr_stock_by_location": stock_by_location,
        },
    )


def stock_transfer_view(request):
    init_db()
    rows = [
        {
            "transfer_no": "TR-00067",
            "transfer_date": "24/02/2026",
            "from_location": "Main Warehouse",
            "to_location": "Store A",
            "status": "Sent",
            "remarks": "Urgent stock needed",
            "has_discrepancy": "No",
            "discrepancy_remarks": "",
        }
    ]
    return render_page(
        request,
        "stock_transfer.html",
        "Stock Transfer",
        "stock_transfer",
        inventory_open=True,
        stock_open=True,
        stock_section=True,
        extra={
            "st_today": date.today().isoformat(),
            "st_rows": rows,
            "st_locations": ["Main Warehouse", "Store A", "Store B", "Store C"],
            "st_statuses": ["Draft", "Sent", "Received", "Cancelled"],
        },
    )


def stock_transfer_new_view(request):
    init_db()
    existing = list(StockTransfer.objects.values_list("transfer_no", flat=True))
    next_no = _next_doc_number("TR-", existing)
    return render_page(
        request,
        "stock_transfer_form.html",
        "Product Transfer",
        "stock_transfer",
        inventory_open=True,
        stock_open=True,
        stock_section=True,
        extra={
            "st_today": date.today().isoformat(),
            "st_next_no": next_no,
            "st_locations": ["Main Warehouse", "Store A", "Store B", "Store C"],
            "st_products": _transaction_product_options(),
            "st_stock_by_location": _inventory_stock_map(),
        },
    )


def stock_adjustment_view(request):
    init_db()
    rows = [
        {
            "adjust_no": "SA-00032",
            "date": "24/02/2026",
            "location": "Branch Store",
            "remarks": "Adjusted 2 due to damage",
            "create_user": "Admin",
            "create_date": "24/02/2026",
        }
    ]
    return render_page(
        request,
        "stock_adjustment.html",
        "Stock Adjustment",
        "stock_adjustment",
        inventory_open=True,
        stock_open=True,
        stock_section=True,
        extra={
            "sa_today": date.today().isoformat(),
            "sa_rows": rows,
            "sa_locations": ["Main Warehouse", "Branch Store", "Store A", "Store B"],
        },
    )


def stock_adjustment_new_view(request):
    init_db()
    existing = list(StockAdjustment.objects.values_list("adjustment_no", flat=True))
    next_no = _next_doc_number("SA-", existing)
    return render_page(
        request,
        "stock_adjustment_form.html",
        "Add/Edit Stock Adjustment",
        "stock_adjustment",
        inventory_open=True,
        stock_open=True,
        stock_section=True,
        extra={
            "sa_today": date.today().isoformat(),
            "sa_next_no": next_no,
            "sa_locations": ["Main Warehouse", "Branch Store", "Store A", "Store B"],
            "sa_products": _transaction_product_options(),
            "sa_stock_by_location": _inventory_stock_map(),
        },
    )


def stock_take_view(request):
    init_db()
    rows = [
        {
            "stock_count_no": "ST-00281",
            "stock_count_date": "28/02/2026",
            "location_code": "HQ",
            "stock_take_status": "Finalized",
            "remarks": "Month-end inventory count",
            "user_name": "Admin",
            "last_stock_take_date": "31/01/2026",
        }
    ]
    return render_page(
        request,
        "stock_take.html",
        "Stock Take",
        "stock_take",
        inventory_open=True,
        stock_open=True,
        stock_section=True,
        extra={
            "stk_today": date.today().isoformat(),
            "stk_rows": rows,
            "stk_locations": ["HQ", "Main Warehouse", "Store A", "Store B"],
            "stk_statuses": ["Pending", "Finalized", "Cancelled"],
        },
    )


def stock_take_new_view(request):
    init_db()
    location_defaults = ["HQ", "Main Warehouse", "Store A", "Store B"]
    inventory_locations = [
        loc
        for loc in Inventory.objects.exclude(location__exact="")
        .values_list("location", flat=True)
        .distinct()
    ]
    merged_locations = []
    seen_locs = set()
    for loc in location_defaults + inventory_locations:
        name = (loc or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen_locs:
            continue
        seen_locs.add(key)
        merged_locations.append(name)

    inventory_rows = []
    for inv in Inventory.objects.exclude(product_code__exact="").order_by("location", "product_name", "product_code"):
        inventory_rows.append(
            {
                "location": (inv.location or "").strip(),
                "product_code": (inv.product_code or "").strip(),
                "product_name": (inv.product_name or inv.product_code or "").strip(),
                "stock_qty": _to_float(inv.stock_qty, 0),
            }
        )

    return render_page(
        request,
        "stock_take_form.html",
        "Add/Edit Stock Take",
        "stock_take",
        inventory_open=True,
        stock_open=True,
        stock_section=True,
        extra={
            "stk_today": date.today().isoformat(),
            "stk_locations": merged_locations or location_defaults,
            "stk_inventory_rows": inventory_rows,
            "stk_products": _transaction_product_options(),
        },
    )


def analysis_view(request):
    return render_page(request, "analysis.html", "Analysis", "analysis", inventory_open=True)

def sales_analysis_view(request):
    return render_page(
        request,
        "sales_analysis.html",
        "Sales Analysis",
        "sales_analysis",
        inventory_open=True,
        extra={"analysis_open": True},
    )


def stock_analysis_view(request):
    return render_page(
        request,
        "stock_analysis.html",
        "Stock Analysis",
        "stock_analysis",
        inventory_open=True,
        extra={"analysis_open": True},
    )
from django.db.models import Sum, Q
from .models import Inventory, GoodsReceiptItem, SalesOrderItem, Product, SupplierMaster

def stock_analysis_view(request):
    # 1. Get filter parameters
    loc_query = request.GET.get('location', '').strip()
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    product_query = request.GET.get('product', '').strip()
    status_query = request.GET.get('status', '')
    supplier_query = request.GET.get('supplier', '').strip()

    # 2. Fetch all unique suppliers for the dropdown
    # We get names from SupplierMaster to populate the filter dropdown
    all_suppliers = SupplierMaster.objects.all().order_by('name')

    inventory_qs = Inventory.objects.all()

    # Apply Location filter
    if loc_query:
        inventory_qs = inventory_qs.filter(location__icontains=loc_query)

    # Apply Product filter
    if product_query:
        inventory_qs = inventory_qs.filter(
            Q(product_name__icontains=product_query) |
            Q(product_code__icontains=product_query)
        )

    stock_data = []

    for inv in inventory_qs:
        # GET LAST SUPPLIER from database for this specific item
               # ✅ DATE FILTER LOGIC
        date_qs = GoodsReceiptItem.objects.filter(
            product_code=inv.product_code
        )

        if from_date:
            date_qs = date_qs.filter(
                goods_receipt__receipt_date__gte=from_date
            )

        if to_date:
            date_qs = date_qs.filter(
                goods_receipt__receipt_date__lte=to_date
            )

        filtered_gr_item = date_qs.select_related(
            'goods_receipt'
        ).order_by(
            '-goods_receipt__receipt_date'
        ).first()
        # 🚨 If date filter applied and no receipt found in that date range, skip item
        if (from_date or to_date) and not filtered_gr_item:
           continue

        receipt_date = (
            filtered_gr_item.goods_receipt.receipt_date
            if filtered_gr_item else None
        )

        actual_supplier = (
            filtered_gr_item.goods_receipt.supplier
            if filtered_gr_item else "No Supplier"
        )

        # DROPDOWN FILTER LOGIC:
        # Skip this item if a supplier is selected in dropdown but doesn't match database
        if supplier_query and supplier_query != actual_supplier:
            continue

        # STOCK IN (PURCHASE)
        in_qs = GoodsReceiptItem.objects.filter(product_code=inv.product_code)
        if from_date:
            in_qs = in_qs.filter(goods_receipt__receipt_date__gte=from_date)
        if to_date:
            in_qs = in_qs.filter(goods_receipt__receipt_date__lte=to_date)
        stock_in = in_qs.aggregate(total=Sum('accepted_qty'))['total'] or 0

        # STOCK OUT (SALES)
        out_qs = SalesOrderItem.objects.filter(product__product_name=inv.product_name)
        if from_date:
            out_qs = out_qs.filter(sales_order__order_date__gte=from_date)
        if to_date:
            out_qs = out_qs.filter(sales_order__order_date__lte=to_date)
        stock_out = out_qs.aggregate(total=Sum('qty'))['total'] or 0

        # MIN STOCK
        prod_master = PurchaseProduct.objects.filter(code=inv.product_code).first()
        min_stock = 10
        if prod_master and hasattr(prod_master, 'reorder_qty'):
            min_stock = prod_master.reorder_qty

        # STATUS
        current_qty = inv.stock_qty
        if current_qty <= 0:
            status_label = "out"
        elif current_qty <= min_stock:
            status_label = "low"
        else:
            status_label = "available"

        if status_query and status_query != status_label:
            continue

        stock_data.append({
            "product": {
                "name": inv.product_name,
                "location": inv.location,
                "supplier": actual_supplier,
                "min_stock": min_stock
            },
            "date": receipt_date, 
            "purchase_qty": stock_in,
            "sales_qty": stock_out,
            "current_stock": current_qty,
            "status": status_label
        })

    return render_page(
        request,
        "stock_analysis.html",
        "Stock Analysis",
        "stock_analysis",
        inventory_open=True,
        extra={
            "analysis_open": True,
            "stock_data": stock_data,
            "all_suppliers": all_suppliers # Pass list to dropdown
        },
    )

def finance_view(request):
    return render_page(request, "finance.html", "Finance", "finance")


def settings_view(request):
    init_db()
    section = (request.GET.get("section") or "").strip().lower()
    tax_rows = list(
        TaxModuleSetting.objects.order_by("module_label", "module_key").values(
            "module_key", "module_label", "tax_percent", "is_fixed"
        )
    )
    purchase_tax_setting = next(
        (row for row in tax_rows if (row.get("module_key") or "") == "purchase"),
        {"module_key": "purchase", "module_label": "Purchase", "tax_percent": 0, "is_fixed": True},
    )
    purchase_order_setting = next(
        (row for row in tax_rows if (row.get("module_key") or "") == "purchase_order"),
        None,
    )
    if (
        _to_float(purchase_tax_setting.get("tax_percent"), 0) <= 0
        and purchase_order_setting
        and _to_float(purchase_order_setting.get("tax_percent"), 0) > 0
    ):
        purchase_tax_setting = {
            **purchase_tax_setting,
            "tax_percent": _to_float(purchase_order_setting.get("tax_percent"), 0),
        }
    tax_module_rows = [
        row for row in tax_rows if (row.get("module_key") or "") != "purchase"
    ]
    return render_page(
        request,
        "setting.html",
        "Settings",
        "dashboard",
        extra={
            "settings_section": section,
            "tax_module_options": TAX_MODULE_OPTIONS,
            "purchase_tax_setting": purchase_tax_setting,
            "tax_module_rows": tax_module_rows,
        },
    )


@csrf_exempt
@require_http_methods(["POST"])
def tax_settings_save_api(request):
    init_db()
    payload = _json_payload(request)
    purchase_tax = _to_float(payload.get("purchase_tax"), 0)
    modules = payload.get("modules") or []

    if purchase_tax < 0:
        return JsonResponse({"ok": False, "error": "Purchase tax must be 0 or higher."}, status=400)
    if not isinstance(modules, list):
        return JsonResponse({"ok": False, "error": "Modules payload is invalid."}, status=400)

    allowed = {item["key"]: item["label"] for item in TAX_MODULE_OPTIONS}
    non_purchase_keys = [key for key in allowed.keys() if key != "purchase"]
    upserted = []
    module_tax_map = {}
    for row in modules:
        key = (row.get("module_key") or "").strip()
        if not key:
            continue
        module_tax_map[key] = _to_float(row.get("tax_percent"), 0)

    if purchase_tax <= 0 and _to_float(module_tax_map.get("purchase_order"), 0) > 0:
        purchase_tax = _to_float(module_tax_map.get("purchase_order"), 0)

    # Purchase module is the primary tax setting from this UI.
    TaxModuleSetting.objects.update_or_create(
        module_key="purchase",
        defaults={
            "module_label": allowed.get("purchase", "Purchase"),
            "tax_percent": purchase_tax,
            "is_fixed": True,
        },
    )
    upserted.append({"module_key": "purchase", "tax_percent": purchase_tax})

    if "purchase_order" in allowed:
        TaxModuleSetting.objects.update_or_create(
            module_key="purchase_order",
            defaults={
                "module_label": allowed["purchase_order"],
                "tax_percent": purchase_tax,
                "is_fixed": True,
            },
        )
        module_tax_map["purchase_order"] = purchase_tax

    saved_module_keys = set()
    for row in modules:
        module_key = (row.get("module_key") or "").strip()
        if not module_key or module_key not in allowed:
            continue
        tax_percent = _to_float(row.get("tax_percent"), 0)
        if module_key == "purchase_order":
            tax_percent = purchase_tax
        if tax_percent < 0:
            continue
        saved_module_keys.add(module_key)
        TaxModuleSetting.objects.update_or_create(
            module_key=module_key,
            defaults={
                "module_label": allowed[module_key],
                "tax_percent": tax_percent,
                "is_fixed": True,
            },
        )
        upserted.append({"module_key": module_key, "tax_percent": tax_percent})

    TaxModuleSetting.objects.filter(module_key__in=non_purchase_keys).exclude(
        module_key__in=saved_module_keys
    ).delete()

    return JsonResponse({"ok": True, "saved": upserted})


def health_view(request):
    return HttpResponse("ok")


def _json_payload(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


@csrf_exempt
@require_http_methods(["POST"])
def po_add_supplier_api(request):
    init_db()
    payload = _json_payload(request)
    code = (payload.get("code") or "").strip()
    name = (payload.get("name") or "").strip()
    if not code or not name:
        return JsonResponse({"ok": False, "error": "Supplier code and name are required."}, status=400)
    supplier, _created = SupplierMaster.objects.update_or_create(
        code=code,
        defaults={
            "name": name,
            "contact": (payload.get("contact") or "").strip(),
            "address": (payload.get("address") or "").strip(),
            "country": (payload.get("country") or "").strip(),
            "currency": (payload.get("currency") or "INR").strip(),
            "payment_terms": (payload.get("payment_terms") or "Net 30").strip(),
        },
    )
    return JsonResponse(
        {
            "ok": True,
            "supplier": {
                "code": supplier.code,
                "name": supplier.name,
                "contact": supplier.contact,
                "address": supplier.address,
                "country": supplier.country,
                "currency": supplier.currency,
                "payment_terms": supplier.payment_terms,
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def po_add_warehouse_api(request):
    init_db()
    payload = _json_payload(request)
    name = (payload.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "error": "Warehouse name is required."}, status=400)
    warehouse, _created = WarehouseMaster.objects.get_or_create(name=name)
    return JsonResponse({"ok": True, "warehouse": {"name": warehouse.name}})


@csrf_exempt
@require_http_methods(["POST"])
def po_add_product_api(request):
    init_db()
    payload = _json_payload(request)
    code = (payload.get("code") or "").strip()
    name = (payload.get("name") or "").strip()
    if not code or not name:
        return JsonResponse({"ok": False, "error": "Product code and name are required."}, status=400)
    product, _created = PurchaseProduct.objects.update_or_create(
        code=code,
        defaults={
            "name": name,
            "description": (payload.get("description") or name).strip(),
            "unit_price": float(payload.get("unit_price") or 0),
            "tax_percent": float(payload.get("tax_percent") or 0),
        },
    )
    return JsonResponse(
        {
            "ok": True,
            "product": {
                "code": product.code,
                "name": product.name,
                "description": product.description,
                "unit_price": product.unit_price,
                "tax_percent": product.tax_percent,
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def po_save_api(request):
    init_db()
    payload = _json_payload(request)
    po_no = (payload.get("po_no") or "").strip()
    if not po_no:
        existing_po_nos = list(PurchaseOrder.objects.values_list("order_no", flat=True))
        po_no = _next_doc_number("PO-", existing_po_nos)

    supplier_code = (payload.get("supplier_code") or "").strip()
    supplier_name = (payload.get("supplier_name") or "").strip()
    warehouse = (payload.get("warehouse") or "").strip()
    payment_terms = (payload.get("payment_terms") or "").strip()
    currency = (payload.get("currency") or "").strip()
    status = (payload.get("status") or "Draft").strip() or "Draft"
    po_date_text = _to_iso_or_today(payload.get("po_date"))
    invoice_no = (payload.get("invoice_no") or po_no).strip()
    amount = _to_float(payload.get("grand_total"), 0)
    items = payload.get("items") or []
    fixed_purchase_tax = _effective_purchase_tax_percent()

    if supplier_code and not SupplierMaster.objects.filter(code=supplier_code).exists():
        return JsonResponse(
            {"ok": False, "error": "Supplier code is not in Vendor Master List."}, status=400
        )
    if not supplier_name and supplier_code:
        supplier_obj = SupplierMaster.objects.filter(code=supplier_code).first()
        supplier_name = supplier_obj.name if supplier_obj else ""

    po_obj = PurchaseOrder.objects.filter(order_no=po_no).order_by("-id").first()
    if po_obj is None:
        po_obj = PurchaseOrder(order_no=po_no)
    po_obj.order_date = po_date_text
    po_obj.invoice_no = invoice_no
    po_obj.supplier = supplier_name
    po_obj.supplier_code = supplier_code
    po_obj.warehouse = warehouse
    po_obj.payment_terms = payment_terms
    po_obj.currency = currency
    po_obj.status = status
    po_obj.amount = amount
    po_obj.paid_amount = 0
    po_obj.save()

    PurchaseOrderItem.objects.filter(purchase_order=po_obj).delete()
    batch = []
    for item in items:
        product_name = (item.get("product_name") or "").strip()
        if not product_name:
            continue
        qty = _to_float(item.get("qty"), 0)
        unit_price = _to_float(item.get("unit_price"), 0)
        discount_percent = _to_float(item.get("discount_percent"), 0)
        line_total = (qty * unit_price) * (1 - (discount_percent / 100))
        if line_total < 0:
            line_total = 0
        net_total = line_total + (line_total * (fixed_purchase_tax / 100))
        batch.append(
            PurchaseOrderItem(
                purchase_order=po_obj,
                product_code=(item.get("product_code") or "").strip(),
                product_name=product_name,
                description=(item.get("description") or "").strip(),
                qty=qty,
                unit_price=unit_price,
                discount_percent=discount_percent,
                tax_percent=fixed_purchase_tax,
                line_total=line_total,
                net_total=net_total,
            )
        )
    if batch:
        PurchaseOrderItem.objects.bulk_create(batch)

    return JsonResponse({"ok": True, "po_id": po_obj.id, "po_no": po_obj.order_no, "rows_saved": len(batch)})


@csrf_exempt
@require_http_methods(["GET"])
def gr_po_details_api(request):
    init_db()
    po_no = (request.GET.get("po_no") or "").strip()
    if not po_no:
        return JsonResponse({"ok": False, "error": "PO Number is required."}, status=400)

    po_obj = PurchaseOrder.objects.filter(order_no=po_no).order_by("-id").first()
    if po_obj is None:
        return JsonResponse({"ok": False, "error": "PO not found."}, status=404)
    po_status = (po_obj.status or "").strip().lower()
    if po_status not in {"approved", "partially received"}:
        return JsonResponse(
            {"ok": False, "error": "Only Approved or Partially Received PO can be used for Goods Receipt."}, status=400
        )

    receipt_by_code = {}
    for item in GoodsReceiptItem.objects.filter(goods_receipt__purchase_order=po_obj):
        code = (item.product_code or "").strip()
        if not code:
            continue
        receipt_by_code[code] = receipt_by_code.get(code, 0) + _to_float(item.received_qty, 0)

    items = []
    fixed_purchase_tax = _effective_purchase_tax_percent()
    for po_item in po_obj.po_items.all().order_by("id"):
        code = (po_item.product_code or "").strip()
        already_received = receipt_by_code.get(code, 0)
        remaining = max(_to_float(po_item.qty, 0) - already_received, 0)
        items.append(
            {
                "po_item_id": po_item.id,
                "product_code": code,
                "product_name": po_item.product_name,
                "ordered_qty": _to_float(po_item.qty, 0),
                "already_received_qty": already_received,
                "remaining_qty": remaining,
                "unit_price": _to_float(po_item.unit_price, 0),
                "tax_percent": fixed_purchase_tax,
            }
        )

    return JsonResponse(
        {
            "ok": True,
            "po": {
                "po_no": po_obj.order_no,
                "supplier": po_obj.supplier,
                "supplier_code": po_obj.supplier_code or "",
                "warehouse": po_obj.warehouse or "",
                "status": po_obj.status or "",
                "order_date": po_obj.order_date.isoformat(),
                "items": items,
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def gr_save_api(request):
    init_db()
    payload = _json_payload(request)
    po_no = (payload.get("po_no") or "").strip()
    if not po_no:
        return JsonResponse({"ok": False, "error": "PO Number is required."}, status=400)

    po_obj = PurchaseOrder.objects.filter(order_no=po_no).order_by("-id").first()
    if po_obj is None:
        return JsonResponse({"ok": False, "error": "PO not found."}, status=404)
    po_status = (po_obj.status or "").strip().lower()
    if po_status not in {"approved", "partially received"}:
        return JsonResponse(
            {"ok": False, "error": "Only Approved or Partially Received PO can be used for Goods Receipt."}, status=400
        )

    gr_no = (payload.get("gr_no") or "").strip()
    if not gr_no:
        existing_gr_nos = list(GoodsReceipt.objects.values_list("gr_no", flat=True))
        gr_no = _next_doc_number("GR-", existing_gr_nos)

    receipt_date_text = _to_iso_or_today(payload.get("receipt_date"))
    invoice_no = (payload.get("invoice_no") or po_obj.invoice_no or "").strip()
    location = (payload.get("location") or po_obj.warehouse or "").strip()
    status = (payload.get("status") or "Open").strip() or "Open"
    item_rows = payload.get("items") or []
    if not item_rows:
        return JsonResponse({"ok": False, "error": "At least one GR item is required."}, status=400)

    po_items = {
        item.id: item
        for item in PurchaseOrderItem.objects.filter(purchase_order=po_obj).order_by("id")
    }
    if not po_items:
        return JsonResponse({"ok": False, "error": "PO has no item rows."}, status=400)

    received_before = {}
    for item in GoodsReceiptItem.objects.filter(goods_receipt__purchase_order=po_obj):
        key = item.po_item_id
        received_before[key] = received_before.get(key, 0) + _to_float(item.received_qty, 0)

    created_items = []
    subtotal = 0.0
    tax_total = 0.0

    with transaction.atomic():
        gr_obj = GoodsReceipt.objects.create(
            gr_no=gr_no,
            purchase_order=po_obj,
            receipt_date=receipt_date_text,
            invoice_no=invoice_no,
            supplier=po_obj.supplier,
            location=location,
            status=status,
        )

        for row in item_rows:
            po_item_id = int(row.get("po_item_id") or 0)
            po_item = po_items.get(po_item_id)
            if po_item is None:
                continue
            ordered_qty = _to_float(po_item.qty, 0)
            received_qty = _to_float(row.get("received_qty"), 0)
            if received_qty <= 0:
                continue

            damaged_qty = max(_to_float(row.get("damaged_qty"), 0), 0)
            quality_status = (row.get("quality_status") or "Pass").strip().title()
            if quality_status not in {"Pass", "Fail", "Damaged"}:
                quality_status = "Pass"

            if quality_status in {"Fail", "Damaged"}:
                accepted_qty = 0.0
                if damaged_qty <= 0:
                    damaged_qty = received_qty
            else:
                accepted_qty = max(received_qty - damaged_qty, 0)

            prior = received_before.get(po_item_id, 0)
            is_over = prior + received_qty > ordered_qty
            line_total = received_qty * _to_float(po_item.unit_price, 0)
            net_total = line_total + (line_total * (_to_float(po_item.tax_percent, 0) / 100))

            created = GoodsReceiptItem.objects.create(
                goods_receipt=gr_obj,
                po_item=po_item,
                product_code=po_item.product_code or "",
                product_name=po_item.product_name,
                ordered_qty=ordered_qty,
                received_qty=received_qty,
                accepted_qty=accepted_qty,
                damaged_qty=damaged_qty,
                quality_status=quality_status,
                unit_price=_to_float(po_item.unit_price, 0),
                tax_percent=_to_float(po_item.tax_percent, 0),
                line_total=line_total,
                net_total=net_total,
                is_over_delivery=is_over,
            )
            created_items.append(created)
            subtotal += line_total
            tax_total += max(net_total - line_total, 0)
            received_before[po_item_id] = prior + received_qty

            inventory_row = Inventory.objects.filter(
                product_code=po_item.product_code or "", location=location
            ).first()
            if inventory_row is None:
                inventory_row = Inventory(
                    product_code=po_item.product_code or "",
                    product_name=po_item.product_name,
                    location=location,
                    stock_qty=0,
                )
            inventory_row.product_name = po_item.product_name
            inventory_row.stock_qty = _to_float(inventory_row.stock_qty, 0) + accepted_qty
            inventory_row.save()

            product_row = PurchaseProduct.objects.filter(code=po_item.product_code or "").first()
            if product_row:
                product_row.name = po_item.product_name
                product_row.save(update_fields=["name"])

        if not created_items:
            gr_obj.delete()
            return JsonResponse(
                {"ok": False, "error": "Enter received quantity for at least one line item."},
                status=400,
            )

        total_ordered = 0.0
        total_received = 0.0
        for item in po_items.values():
            total_ordered += _to_float(item.qty, 0)
            total_received += received_before.get(item.id, 0)
        if total_received >= total_ordered and total_ordered > 0:
            po_obj.status = "Completed"
        else:
            po_obj.status = "Partially Received"
        po_obj.save(update_fields=["status"])

    return JsonResponse(
        {
            "ok": True,
            "gr_no": gr_no,
            "po_no": po_obj.order_no,
            "po_status": po_obj.status,
            "subtotal": subtotal,
            "tax": tax_total,
            "net_total": subtotal + tax_total,
            "rows_saved": len(created_items),
        }
    )


@csrf_exempt
@require_http_methods(["GET"])
def gor_gr_details_api(request):
    init_db()
    gr_no = (request.GET.get("gr_no") or "").strip()
    if not gr_no:
        return JsonResponse({"ok": False, "error": "Goods Receipt Number is required."}, status=400)

    gr_obj = GoodsReceipt.objects.filter(gr_no=gr_no).order_by("-id").first()
    if gr_obj is None:
        return JsonResponse({"ok": False, "error": "Goods Receipt not found."}, status=404)

    returned_qty_by_source = {}
    for item in GoodsReturnItem.objects.filter(goods_return__original_gr=gr_obj):
        source_id = item.source_gr_item_id
        returned_qty_by_source[source_id] = returned_qty_by_source.get(source_id, 0) + _to_float(item.quantity, 0)

    items = []
    for source in gr_obj.items.all().order_by("id"):
        accepted = _to_float(source.accepted_qty, 0)
        already_returned = returned_qty_by_source.get(source.id, 0)
        returnable = max(accepted - already_returned, 0)
        items.append(
            {
                "gr_item_id": source.id,
                "product_code": source.product_code or "",
                "product_name": source.product_name or "",
                "accepted_qty": accepted,
                "already_returned_qty": already_returned,
                "returnable_qty": returnable,
                "unit_price": _to_float(source.unit_price, 0),
                "tax_percent": _to_float(source.tax_percent, 0),
            }
        )

    return JsonResponse(
        {
            "ok": True,
            "gr": {
                "gr_no": gr_obj.gr_no,
                "supplier": gr_obj.supplier,
                "invoice_no": gr_obj.invoice_no,
                "location": gr_obj.location or "",
                "receipt_date": gr_obj.receipt_date.isoformat(),
                "items": items,
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def gor_save_api(request):
    init_db()
    payload = _json_payload(request)
    gr_no = (payload.get("gr_no") or "").strip()
    if not gr_no:
        return JsonResponse({"ok": False, "error": "Goods Receipt Number is required."}, status=400)

    gr_obj = GoodsReceipt.objects.filter(gr_no=gr_no).order_by("-id").first()
    if gr_obj is None:
        return JsonResponse({"ok": False, "error": "Goods Receipt not found."}, status=404)

    return_no = (payload.get("return_no") or "").strip()
    if not return_no:
        existing = list(GoodsReturn.objects.values_list("return_no", flat=True))
        return_no = _next_doc_number("RTN-", existing)

    return_date = _to_iso_or_today(payload.get("return_date"))
    status = (payload.get("status") or "Pending Vendor Confirmation").strip() or "Pending Vendor Confirmation"
    invoice_no = (payload.get("invoice_no") or gr_obj.invoice_no or "").strip()
    location = (payload.get("location") or gr_obj.location or "").strip()
    item_rows = payload.get("items") or []
    if not item_rows:
        return JsonResponse({"ok": False, "error": "At least one return item is required."}, status=400)

    source_items = {item.id: item for item in gr_obj.items.all()}
    if not source_items:
        return JsonResponse({"ok": False, "error": "Selected GR has no item rows."}, status=400)

    already_returned = {}
    for existing_item in GoodsReturnItem.objects.filter(goods_return__original_gr=gr_obj):
        src_id = existing_item.source_gr_item_id
        already_returned[src_id] = already_returned.get(src_id, 0) + _to_float(existing_item.quantity, 0)

    total_amount = 0.0
    subtotal = 0.0
    tax_total = 0.0
    valid_reasons = {"Damaged", "Wrong Item", "Excess", "Expired", "Quality Fail", "Other"}
    prepared_rows = []
    for row in item_rows:
        try:
            gr_item_id = int(row.get("gr_item_id") or 0)
        except (TypeError, ValueError):
            gr_item_id = 0
        source = source_items.get(gr_item_id)
        if source is None:
            continue

        qty = _to_float(row.get("quantity"), 0)
        if qty <= 0:
            continue

        max_allowed = max(_to_float(source.accepted_qty, 0) - already_returned.get(gr_item_id, 0), 0)
        if qty > max_allowed:
            return JsonResponse(
                {"ok": False, "error": f"Return qty exceeds available qty for {source.product_name}."},
                status=400,
            )

        reason = (row.get("reason") or "").strip()
        if not reason:
            return JsonResponse(
                {"ok": False, "error": f"Reason is required for {source.product_name}."},
                status=400,
            )
        if reason not in valid_reasons:
            reason = "Other"

        condition = (row.get("condition") or "Damaged").strip() or "Damaged"
        line_total = qty * _to_float(source.unit_price, 0)
        net_total = line_total + (line_total * (_to_float(source.tax_percent, 0) / 100))
        subtotal += line_total
        tax_total += max(net_total - line_total, 0)
        prepared_rows.append(
            {
                "source": source,
                "qty": qty,
                "reason": reason,
                "condition": condition,
                "line_total": line_total,
                "net_total": net_total,
            }
        )
        already_returned[gr_item_id] = already_returned.get(gr_item_id, 0) + qty

    if not prepared_rows:
        return JsonResponse(
            {"ok": False, "error": "Enter return quantity for at least one line item."},
            status=400,
        )

    with transaction.atomic():
        return_obj = GoodsReturn.objects.create(
            return_no=return_no,
            original_gr=gr_obj,
            supplier=gr_obj.supplier,
            return_date=return_date,
            invoice_no=invoice_no,
            location=location,
            status=status,
            total_amount=0,
        )

        for prepared in prepared_rows:
            source = prepared["source"]
            GoodsReturnItem.objects.create(
                goods_return=return_obj,
                source_gr_item=source,
                product_code=source.product_code or "",
                product_name=source.product_name or "",
                quantity=prepared["qty"],
                reason=prepared["reason"],
                condition=prepared["condition"],
                unit_price=_to_float(source.unit_price, 0),
                tax_percent=_to_float(source.tax_percent, 0),
                line_total=prepared["line_total"],
                net_total=prepared["net_total"],
            )

        total_amount = subtotal + tax_total
        return_obj.total_amount = total_amount
        return_obj.save(update_fields=["total_amount"])

    return JsonResponse(
        {
            "ok": True,
            "return_no": return_obj.return_no,
            "status": return_obj.status,
            "subtotal": subtotal,
            "tax": tax_total,
            "net_total": total_amount,
            "rows_saved": len(prepared_rows),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def gor_approve_api(request):
    init_db()
    payload = _json_payload(request)
    return_no = (payload.get("return_no") or "").strip()
    if not return_no:
        return JsonResponse({"ok": False, "error": "Return Number is required."}, status=400)

    return_obj = GoodsReturn.objects.filter(return_no=return_no).order_by("-id").first()
    if return_obj is None:
        return JsonResponse({"ok": False, "error": "Goods Return not found."}, status=404)

    if (return_obj.status or "").strip().lower() == "approved":
        return JsonResponse(
            {"ok": True, "return_no": return_obj.return_no, "status": return_obj.status, "message": "Already approved."}
        )

    rows = list(return_obj.items.all())
    if not rows:
        return JsonResponse({"ok": False, "error": "No return items found."}, status=400)

    inventory_updates = []
    for row in rows:
        inventory_row = Inventory.objects.filter(
            product_code=row.product_code or "",
            location=return_obj.location or "",
        ).first()
        if inventory_row is None:
            return JsonResponse(
                {"ok": False, "error": f"Inventory row missing for {row.product_name} at {return_obj.location}."},
                status=400,
            )
        current_stock = _to_float(inventory_row.stock_qty, 0)
        if row.quantity > current_stock:
            return JsonResponse(
                {
                    "ok": False,
                    "error": f"Insufficient stock for {row.product_name}. Stock {current_stock:.2f}, return {row.quantity:.2f}.",
                },
                status=400,
            )
        inventory_updates.append((inventory_row, current_stock - _to_float(row.quantity, 0)))

    with transaction.atomic():
        for inventory_row, updated_stock in inventory_updates:
            inventory_row.stock_qty = updated_stock
            inventory_row.save(update_fields=["stock_qty"])

        existing_note = DebitNote.objects.filter(goods_return=return_obj).first()
        if existing_note is None:
            existing = list(DebitNote.objects.values_list("note_no", flat=True))
            note_no = _next_doc_number("DN-", existing)
            note = DebitNote.objects.create(
                note_no=note_no,
                goods_return=return_obj,
                supplier=return_obj.supplier,
                note_date=return_obj.return_date,
                amount=_to_float(return_obj.total_amount, 0),
                status="Open",
            )
        else:
            note = existing_note

        SupplierLedgerEntry.objects.create(
            supplier=return_obj.supplier,
            entry_date=date.today(),
            document_type="Debit Note",
            document_no=note.note_no,
            amount=_to_float(return_obj.total_amount, 0),
            dr_cr="DR",
            remarks=f"Goods return {return_obj.return_no} approved; payable reduced.",
        )

        return_obj.status = "Approved"
        return_obj.save(update_fields=["status"])

    return JsonResponse(
        {
            "ok": True,
            "return_no": return_obj.return_no,
            "status": return_obj.status,
            "debit_note_no": note.note_no,
            "amount": return_obj.total_amount,
        }
    )


@csrf_exempt
@require_http_methods(["GET"])
def pi_gr_details_api(request):
    init_db()
    gr_no = (request.GET.get("gr_no") or "").strip()
    if not gr_no:
        return JsonResponse({"ok": False, "error": "GR Number is required."}, status=400)

    gr_obj = GoodsReceipt.objects.select_related("purchase_order").filter(gr_no=gr_no).order_by("-id").first()
    if gr_obj is None:
        return JsonResponse({"ok": False, "error": "Goods Receipt not found."}, status=404)

    billed_by_gr_item = {}
    for item in PurchaseInvoiceEntryItem.objects.filter(gr_item__goods_receipt=gr_obj):
        gr_item_id = item.gr_item_id
        billed_by_gr_item[gr_item_id] = billed_by_gr_item.get(gr_item_id, 0) + _to_float(item.billed_qty, 0)

    returned_by_gr_item = {}
    for item in GoodsReturnItem.objects.filter(
        goods_return__original_gr=gr_obj, goods_return__status="Approved"
    ):
        gr_item_id = item.source_gr_item_id
        returned_by_gr_item[gr_item_id] = returned_by_gr_item.get(gr_item_id, 0) + _to_float(item.quantity, 0)

    items = []
    for src in gr_obj.items.select_related("po_item").all().order_by("id"):
        received_qty = _to_float(src.received_qty, 0)
        returned_qty = returned_by_gr_item.get(src.id, 0)
        retained_qty = max(received_qty - returned_qty, 0)
        already_billed = billed_by_gr_item.get(src.id, 0)
        remaining = max(retained_qty - already_billed, 0)
        items.append(
            {
                "gr_item_id": src.id,
                "po_item_id": src.po_item_id or 0,
                "product_code": src.product_code or "",
                "product_name": src.product_name or "",
                "received_qty": received_qty,
                "returned_qty": returned_qty,
                "retained_qty": retained_qty,
                "already_billed_qty": already_billed,
                "billable_qty": remaining,
                "unit_price_po": _to_float(src.po_item.unit_price if src.po_item else src.unit_price, 0),
                "unit_price_gr": _to_float(src.unit_price, 0),
                "tax_percent": _to_float(src.tax_percent, 0),
            }
        )

    return JsonResponse(
        {
            "ok": True,
            "gr": {
                "gr_no": gr_obj.gr_no,
                "po_no": gr_obj.purchase_order.order_no if gr_obj.purchase_order_id else "",
                "supplier": gr_obj.supplier,
                "invoice_no": gr_obj.invoice_no,
                "location": gr_obj.location or "",
                "receipt_date": gr_obj.receipt_date.isoformat(),
                "items": items,
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def pi_save_api(request):
    init_db()
    payload = _json_payload(request)
    gr_no = (payload.get("gr_no") or "").strip()
    po_no = (payload.get("po_no") or "").strip()
    supplier_invoice_no = (payload.get("supplier_invoice_no") or "").strip()
    if not gr_no or not po_no or not supplier_invoice_no:
        return JsonResponse(
            {"ok": False, "error": "PO Number, GR Number and Supplier Invoice Number are required."},
            status=400,
        )

    if PurchaseInvoiceEntry.objects.filter(supplier_invoice_no=supplier_invoice_no).exists():
        return JsonResponse({"ok": False, "error": "Supplier Invoice Number already exists."}, status=400)

    po_obj = PurchaseOrder.objects.filter(order_no=po_no).order_by("-id").first()
    if po_obj is None:
        return JsonResponse({"ok": False, "error": "PO not found."}, status=404)
    gr_obj = GoodsReceipt.objects.select_related("purchase_order").filter(gr_no=gr_no).order_by("-id").first()
    if gr_obj is None:
        return JsonResponse({"ok": False, "error": "GR not found."}, status=404)
    if not gr_obj.purchase_order_id or gr_obj.purchase_order.order_no != po_no:
        return JsonResponse({"ok": False, "error": "GR does not belong to the selected PO."}, status=400)

    tran_no = (payload.get("tran_no") or "").strip()
    if not tran_no:
        existing = list(PurchaseInvoiceEntry.objects.values_list("tran_no", flat=True))
        tran_no = _next_doc_number("PINV-", existing)

    invoice_date = _to_iso_or_today(payload.get("invoice_date"))
    location = (payload.get("location") or gr_obj.location or po_obj.warehouse or "").strip()
    paid_amount = max(_to_float(payload.get("paid_amount"), 0), 0)
    entered_invoice_amount = _to_float(payload.get("invoice_amount"), 0)
    item_rows = payload.get("items") or []
    if not item_rows:
        return JsonResponse({"ok": False, "error": "At least one billed item is required."}, status=400)

    gr_items = {
        item.id: item for item in gr_obj.items.select_related("po_item").all()
    }
    already_billed = {}
    for billed in PurchaseInvoiceEntryItem.objects.filter(gr_item__goods_receipt=gr_obj):
        gid = billed.gr_item_id
        already_billed[gid] = already_billed.get(gid, 0) + _to_float(billed.billed_qty, 0)

    returned_by_gr_item = {}
    for returned in GoodsReturnItem.objects.filter(
        goods_return__original_gr=gr_obj, goods_return__status="Approved"
    ):
        gid = returned.source_gr_item_id
        returned_by_gr_item[gid] = returned_by_gr_item.get(gid, 0) + _to_float(returned.quantity, 0)

    prepared_rows = []
    sub_total = 0.0
    tax_total = 0.0

    for row in item_rows:
        try:
            gr_item_id = int(row.get("gr_item_id") or 0)
        except (TypeError, ValueError):
            gr_item_id = 0
        src = gr_items.get(gr_item_id)
        if src is None:
            continue

        billed_qty = _to_float(row.get("billed_qty"), 0)
        if billed_qty <= 0:
            continue

        retained_qty = max(
            _to_float(src.received_qty, 0) - returned_by_gr_item.get(gr_item_id, 0), 0
        )
        max_billable = max(retained_qty - already_billed.get(gr_item_id, 0), 0)
        if billed_qty > max_billable:
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        f"Billed qty exceeds retained qty for {src.product_name}. "
                        f"Retained balance: {max_billable:.2f}"
                    ),
                },
                status=400,
            )

        billed_price = _to_float(row.get("unit_price"), _to_float(src.unit_price, 0))
        po_price = _to_float(src.po_item.unit_price if src.po_item else src.unit_price, 0)
        if abs(billed_price - po_price) > 0.0001:
            return JsonResponse(
                {"ok": False, "error": f"Price Mismatch Alert for {src.product_name}. PO price {po_price:.2f}, billed {billed_price:.2f}."},
                status=400,
            )

        tax_percent = _to_float(row.get("tax_percent"), _to_float(src.tax_percent, 0))
        line_subtotal = billed_qty * billed_price
        line_net = line_subtotal + (line_subtotal * (tax_percent / 100))
        sub_total += line_subtotal
        tax_total += max(line_net - line_subtotal, 0)

        prepared_rows.append(
            {
                "src": src,
                "billed_qty": billed_qty,
                "unit_price": billed_price,
                "tax_percent": tax_percent,
                "sub_total": line_subtotal,
                "net_total": line_net,
            }
        )
        already_billed[gr_item_id] = already_billed.get(gr_item_id, 0) + billed_qty

    if not prepared_rows:
        return JsonResponse({"ok": False, "error": "Enter billed quantity for at least one line item."}, status=400)

    net_total = sub_total + tax_total
    if entered_invoice_amount > 0 and abs(entered_invoice_amount - net_total) > 0.0001:
        return JsonResponse(
            {
                "ok": False,
                "error": f"Price Mismatch Alert. Expected invoice amount {net_total:.2f}, entered {entered_invoice_amount:.2f}.",
            },
            status=400,
        )

    balance_amount = max(net_total - paid_amount, 0)
    payment_status = "Paid" if balance_amount <= 0 else ("Partial" if paid_amount > 0 else "Not Paid")
    status = "Approved"

    with transaction.atomic():
        header = PurchaseInvoiceEntry.objects.create(
            tran_no=tran_no,
            po_no=po_no,
            gr_no=gr_no,
            supplier_invoice_no=supplier_invoice_no,
            invoice_date=invoice_date,
            supplier=gr_obj.supplier,
            location=location,
            status=status,
            payment_status=payment_status,
            sub_total=sub_total,
            tax_total=tax_total,
            net_total=net_total,
            paid_amount=paid_amount,
            balance_amount=balance_amount,
        )

        for prepared in prepared_rows:
            src = prepared["src"]
            PurchaseInvoiceEntryItem.objects.create(
                invoice_entry=header,
                gr_item=src,
                po_item=src.po_item if src.po_item_id else None,
                product_code=src.product_code or "",
                product_name=src.product_name or "",
                billed_qty=prepared["billed_qty"],
                unit_price=prepared["unit_price"],
                tax_percent=prepared["tax_percent"],
                sub_total=prepared["sub_total"],
                net_total=prepared["net_total"],
            )

        PurchaseInvoice.objects.create(
            invoice_no=supplier_invoice_no,
            invoice_date=invoice_date,
            supplier=gr_obj.supplier,
            total_amount=net_total,
            paid_amount=paid_amount,
        )

        SupplierLedgerEntry.objects.create(
            supplier=gr_obj.supplier,
            entry_date=invoice_date,
            document_type="Purchase Invoice",
            document_no=supplier_invoice_no,
            amount=net_total,
            dr_cr="CR",
            remarks=f"AP created via invoice {tran_no}.",
        )

    return JsonResponse(
        {
            "ok": True,
            "tran_no": tran_no,
            "status": status,
            "payment_status": payment_status,
            "sub_total": sub_total,
            "tax": tax_total,
            "net_total": net_total,
            "paid_amount": paid_amount,
            "balance_amount": balance_amount,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def sr_save_api(request):
    init_db()
    payload = _json_payload(request)
    request_no = (payload.get("request_no") or "").strip()
    if not request_no:
        existing = list(StockRequest.objects.values_list("request_no", flat=True))
        request_no = _next_doc_number("SR-", existing)
    request_date = _to_iso_or_today(payload.get("request_date"))
    from_location = (payload.get("from_location") or "").strip()
    to_location = (payload.get("to_location") or "").strip()
    remarks = (payload.get("remarks") or "").strip()
    status = (payload.get("status") or "Draft").strip() or "Draft"
    if status not in {"Draft", "Pending Approval", "Submitted"}:
        status = "Draft"
    items = payload.get("items") or []

    if not from_location or not to_location:
        return JsonResponse({"ok": False, "error": "From and To locations are required."}, status=400)
    if from_location == to_location:
        return JsonResponse({"ok": False, "error": "From and To locations must be different."}, status=400)

    prepared = []
    for row in items:
        total_qty = _to_float(row.get("total_qty"), 0)
        if total_qty <= 0:
            continue
        prepared.append(
            {
                "product_code": (row.get("product_code") or "").strip(),
                "product_name": (row.get("product_name") or "").strip(),
                "carton_qty": _to_float(row.get("carton_qty"), 0),
                "loose_qty": _to_float(row.get("loose_qty"), 0),
                "total_qty": total_qty,
            }
        )
    if not prepared:
        return JsonResponse({"ok": False, "error": "Add at least one item with quantity > 0."}, status=400)

    try:
        with transaction.atomic():
            header = StockRequest.objects.create(
                request_no=request_no,
                request_date=request_date,
                from_location=from_location,
                to_location=to_location,
                status=status,
                remarks=remarks,
                created_by=(payload.get("created_by") or "Admin").strip() or "Admin",
                created_date=date.today().isoformat(),
            )
            StockRequestItem.objects.bulk_create(
                [
                    StockRequestItem(
                        stock_request=header,
                        product_code=row["product_code"],
                        product_name=row["product_name"],
                        carton_qty=row["carton_qty"],
                        loose_qty=row["loose_qty"],
                        total_qty=row["total_qty"],
                    )
                    for row in prepared
                ]
            )
    except IntegrityError:
        # If request number already exists (stale form), retry once with next sequence.
        existing = list(StockRequest.objects.values_list("request_no", flat=True))
        request_no = _next_doc_number("SR-", existing)
        with transaction.atomic():
            header = StockRequest.objects.create(
                request_no=request_no,
                request_date=request_date,
                from_location=from_location,
                to_location=to_location,
                status=status,
                remarks=remarks,
                created_by=(payload.get("created_by") or "Admin").strip() or "Admin",
                created_date=date.today().isoformat(),
            )
            StockRequestItem.objects.bulk_create(
                [
                    StockRequestItem(
                        stock_request=header,
                        product_code=row["product_code"],
                        product_name=row["product_name"],
                        carton_qty=row["carton_qty"],
                        loose_qty=row["loose_qty"],
                        total_qty=row["total_qty"],
                    )
                    for row in prepared
                ]
            )
    return JsonResponse(
        {
            "ok": True,
            "request_no": header.request_no,
            "status": header.status,
            "rows_saved": len(prepared),
            "note": "Stock request saved. Inventory is unchanged.",
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def st_save_api(request):
    init_db()
    payload = _json_payload(request)
    transfer_no = (payload.get("transfer_no") or "").strip()
    if not transfer_no:
        existing = list(StockTransfer.objects.values_list("transfer_no", flat=True))
        transfer_no = _next_doc_number("TR-", existing)
    transfer_date = _to_iso_or_today(payload.get("transfer_date"))
    from_location = (payload.get("from_location") or "").strip()
    to_location = (payload.get("to_location") or "").strip()
    remarks = (payload.get("remarks") or "").strip()
    items = payload.get("items") or []

    if not from_location or not to_location:
        return JsonResponse({"ok": False, "error": "From and To locations are required."}, status=400)
    if from_location == to_location:
        return JsonResponse({"ok": False, "error": "From and To locations must be different."}, status=400)

    prepared = []
    for row in items:
        qty = _to_float(row.get("qty"), 0)
        if qty <= 0:
            continue
        prepared.append(
            {
                "product_code": (row.get("product_code") or "").strip(),
                "product_name": (row.get("product_name") or "").strip(),
                "qty": qty,
            }
        )
    if not prepared:
        return JsonResponse({"ok": False, "error": "Add at least one item with quantity > 0."}, status=400)

    try:
        with transaction.atomic():
            header = StockTransfer.objects.create(
                transfer_no=transfer_no,
                transfer_date=transfer_date,
                from_location=from_location,
                to_location=to_location,
                status="Draft",
                remarks=remarks,
            )
            StockTransferItem.objects.bulk_create(
                [
                    StockTransferItem(
                        stock_transfer=header,
                        product_code=row["product_code"],
                        product_name=row["product_name"],
                        qty=row["qty"],
                    )
                    for row in prepared
                ]
            )
    except IntegrityError:
        existing = list(StockTransfer.objects.values_list("transfer_no", flat=True))
        transfer_no = _next_doc_number("TR-", existing)
        with transaction.atomic():
            header = StockTransfer.objects.create(
                transfer_no=transfer_no,
                transfer_date=transfer_date,
                from_location=from_location,
                to_location=to_location,
                status="Draft",
                remarks=remarks,
            )
            StockTransferItem.objects.bulk_create(
                [
                    StockTransferItem(
                        stock_transfer=header,
                        product_code=row["product_code"],
                        product_name=row["product_name"],
                        qty=row["qty"],
                    )
                    for row in prepared
                ]
            )
    return JsonResponse({"ok": True, "transfer_no": header.transfer_no, "status": header.status, "rows_saved": len(prepared)})


@csrf_exempt
@require_http_methods(["POST"])
def st_confirm_api(request):
    init_db()
    payload = _json_payload(request)
    transfer_no = (payload.get("transfer_no") or "").strip()
    if not transfer_no:
        return JsonResponse({"ok": False, "error": "Transfer Number is required."}, status=400)

    header = StockTransfer.objects.filter(transfer_no=transfer_no).order_by("-id").first()
    if header is None:
        return JsonResponse({"ok": False, "error": "Stock transfer not found."}, status=404)
    if (header.status or "").strip().lower() in {"sent", "received"}:
        return JsonResponse({"ok": True, "transfer_no": header.transfer_no, "status": header.status, "message": "Already processed."})

    rows = list(header.items.all())
    if not rows:
        return JsonResponse({"ok": False, "error": "Transfer has no items."}, status=400)

    from_updates = []
    to_updates = []
    for row in rows:
        src_inv = Inventory.objects.filter(product_code=row.product_code, location=header.from_location).first()
        if src_inv is None:
            return JsonResponse(
                {"ok": False, "error": f"Source stock missing for {row.product_name} at {header.from_location}."},
                status=400,
            )
        src_stock = _to_float(src_inv.stock_qty, 0)
        if row.qty > src_stock:
            return JsonResponse(
                {"ok": False, "error": f"Insufficient source stock for {row.product_name}. Available {src_stock:.2f}, transfer {row.qty:.2f}."},
                status=400,
            )
        dst_inv = Inventory.objects.filter(product_code=row.product_code, location=header.to_location).first()
        if dst_inv is None:
            dst_inv = Inventory(
                product_code=row.product_code,
                product_name=row.product_name,
                location=header.to_location,
                stock_qty=0,
            )
        from_updates.append((src_inv, src_stock - row.qty))
        to_updates.append((dst_inv, _to_float(dst_inv.stock_qty, 0) + row.qty, row.product_name))

    with transaction.atomic():
        for inv_row, new_qty in from_updates:
            inv_row.stock_qty = new_qty
            inv_row.save(update_fields=["stock_qty"])
        for inv_row, new_qty, pname in to_updates:
            inv_row.product_name = pname
            inv_row.stock_qty = new_qty
            inv_row.save()
        header.status = "Sent"
        header.save(update_fields=["status"])

    return JsonResponse(
        {
            "ok": True,
            "transfer_no": header.transfer_no,
            "status": header.status,
            "note": "Inventory moved: source decreased, destination increased.",
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def sa_save_api(request):
    init_db()
    payload = _json_payload(request)
    adjustment_no = (payload.get("adjustment_no") or "").strip()
    if not adjustment_no:
        existing = list(StockAdjustment.objects.values_list("adjustment_no", flat=True))
        adjustment_no = _next_doc_number("SA-", existing)
    adjustment_date = _to_iso_or_today(payload.get("adjustment_date"))
    location = (payload.get("location") or "").strip()
    remarks = (payload.get("remarks") or "").strip()
    items = payload.get("items") or []
    if not location:
        return JsonResponse({"ok": False, "error": "Location is required."}, status=400)

    prepared = []
    for row in items:
        qty = _to_float(row.get("adjustment_qty"), 0)
        if qty <= 0:
            continue
        sign = (row.get("adjustment_sign") or "-").strip()
        if sign not in {"+", "-"}:
            sign = "-"
        pcode = (row.get("product_code") or "").strip()
        pname = (row.get("product_name") or "").strip()
        inv = Inventory.objects.filter(product_code=pcode, location=location).first()
        old_qty = _to_float(inv.stock_qty if inv else 0, 0)
        new_qty = old_qty + qty if sign == "+" else old_qty - qty
        if new_qty < 0:
            return JsonResponse({"ok": False, "error": f"Negative stock not allowed for {pname or pcode}."}, status=400)
        prepared.append(
            {
                "product_code": pcode,
                "product_name": pname,
                "old_qty": old_qty,
                "adjustment_sign": sign,
                "adjustment_qty": qty,
                "new_qty": new_qty,
                "reason": (row.get("reason") or "Manual Correction").strip() or "Manual Correction",
            }
        )

    if not prepared:
        return JsonResponse({"ok": False, "error": "Add at least one adjustment item with qty > 0."}, status=400)

    try:
        with transaction.atomic():
            header = StockAdjustment.objects.create(
                adjustment_no=adjustment_no,
                adjustment_date=adjustment_date,
                location=location,
                remarks=remarks,
                created_by=(payload.get("created_by") or "Admin").strip() or "Admin",
                created_date=date.today().isoformat(),
            )
            for row in prepared:
                StockAdjustmentItem.objects.create(stock_adjustment=header, **row)
                inv = Inventory.objects.filter(product_code=row["product_code"], location=location).first()
                if inv is None:
                    inv = Inventory(
                        product_code=row["product_code"],
                        product_name=row["product_name"],
                        location=location,
                        stock_qty=0,
                    )
                inv.product_name = row["product_name"]
                inv.stock_qty = row["new_qty"]
                inv.save()
    except IntegrityError:
        existing = list(StockAdjustment.objects.values_list("adjustment_no", flat=True))
        adjustment_no = _next_doc_number("SA-", existing)
        with transaction.atomic():
            header = StockAdjustment.objects.create(
                adjustment_no=adjustment_no,
                adjustment_date=adjustment_date,
                location=location,
                remarks=remarks,
                created_by=(payload.get("created_by") or "Admin").strip() or "Admin",
                created_date=date.today().isoformat(),
            )
            for row in prepared:
                StockAdjustmentItem.objects.create(stock_adjustment=header, **row)
                inv = Inventory.objects.filter(product_code=row["product_code"], location=location).first()
                if inv is None:
                    inv = Inventory(
                        product_code=row["product_code"],
                        product_name=row["product_name"],
                        location=location,
                        stock_qty=0,
                    )
                inv.product_name = row["product_name"]
                inv.stock_qty = row["new_qty"]
                inv.save()
    return JsonResponse({"ok": True, "adjustment_no": header.adjustment_no, "rows_saved": len(prepared)})


@csrf_exempt
@require_http_methods(["POST"])
def stk_save_api(request):
    init_db()
    payload = _json_payload(request)
    stock_take_no = (payload.get("stock_take_no") or "").strip()
    if not stock_take_no:
        existing = list(StockTake.objects.values_list("stock_take_no", flat=True))
        stock_take_no = _next_doc_number("ST-", existing)
    stock_take_date = _to_iso_or_today(payload.get("stock_take_date"))
    location = (payload.get("location") or "").strip()
    remarks = (payload.get("remarks") or "").strip()
    items = payload.get("items") or []
    if not location:
        return JsonResponse({"ok": False, "error": "Location is required."}, status=400)

    prepared = []
    for row in items:
        pcode = (row.get("product_code") or "").strip()
        pname = (row.get("product_name") or "").strip()
        system_qty = _to_float(row.get("system_qty"), 0)
        physical_qty = _to_float(row.get("physical_qty"), 0)
        if pcode == "" and pname == "":
            continue
        prepared.append(
            {
                "product_code": pcode,
                "product_name": pname,
                "system_qty": system_qty,
                "physical_qty": physical_qty,
                "variance": physical_qty - system_qty,
            }
        )
    if not prepared:
        return JsonResponse({"ok": False, "error": "Add at least one stock take line."}, status=400)

    last_take = (
        StockTake.objects.filter(location=location, status="Finalized")
        .order_by("-stock_take_date")
        .values_list("stock_take_date", flat=True)
        .first()
    )
    try:
        with transaction.atomic():
            header = StockTake.objects.create(
                stock_take_no=stock_take_no,
                stock_take_date=stock_take_date,
                location=location,
                status="Pending",
                remarks=remarks,
                user_name=(payload.get("user_name") or "Admin").strip() or "Admin",
                last_stock_take_date=last_take,
            )
            StockTakeItem.objects.bulk_create(
                [StockTakeItem(stock_take=header, **row) for row in prepared]
            )
    except IntegrityError:
        existing = list(StockTake.objects.values_list("stock_take_no", flat=True))
        stock_take_no = _next_doc_number("ST-", existing)
        with transaction.atomic():
            header = StockTake.objects.create(
                stock_take_no=stock_take_no,
                stock_take_date=stock_take_date,
                location=location,
                status="Pending",
                remarks=remarks,
                user_name=(payload.get("user_name") or "Admin").strip() or "Admin",
                last_stock_take_date=last_take,
            )
            StockTakeItem.objects.bulk_create(
                [StockTakeItem(stock_take=header, **row) for row in prepared]
            )
    return JsonResponse({"ok": True, "stock_take_no": header.stock_take_no, "status": header.status, "rows_saved": len(prepared)})


@csrf_exempt
@require_http_methods(["POST"])
def stk_finalize_api(request):
    init_db()
    payload = _json_payload(request)
    stock_take_no = (payload.get("stock_take_no") or "").strip()
    if not stock_take_no:
        return JsonResponse({"ok": False, "error": "Stock Take Number is required."}, status=400)

    header = StockTake.objects.filter(stock_take_no=stock_take_no).order_by("-id").first()
    if header is None:
        return JsonResponse({"ok": False, "error": "Stock take not found."}, status=404)
    if (header.status or "").strip().lower() == "finalized":
        return JsonResponse({"ok": True, "stock_take_no": header.stock_take_no, "status": header.status, "message": "Already finalized."})

    rows = list(header.items.all())
    if not rows:
        return JsonResponse({"ok": False, "error": "Stock take has no items."}, status=400)

    with transaction.atomic():
        for row in rows:
            inv = Inventory.objects.filter(product_code=row.product_code, location=header.location).first()
            if inv is None:
                inv = Inventory(
                    product_code=row.product_code,
                    product_name=row.product_name,
                    location=header.location,
                    stock_qty=0,
                )
            inv.product_name = row.product_name
            inv.stock_qty = _to_float(row.physical_qty, 0)
            inv.save()
        header.status = "Finalized"
        header.last_stock_take_date = header.stock_take_date
        header.save(update_fields=["status", "last_stock_take_date"])

    return JsonResponse({"ok": True, "stock_take_no": header.stock_take_no, "status": header.status, "note": "Inventory reset to physical quantity."})


@csrf_exempt
@require_http_methods(["POST"])
def pi_pay_api(request):
    init_db()
    payload = _json_payload(request)
    tran_no = (payload.get("tran_no") or "").strip()
    amount = _to_float(payload.get("amount"), 0)
    if not tran_no:
        return JsonResponse({"ok": False, "error": "Invoice Tran No is required."}, status=400)
    if amount <= 0:
        return JsonResponse({"ok": False, "error": "Payment amount must be greater than 0."}, status=400)

    invoice = PurchaseInvoiceEntry.objects.filter(tran_no=tran_no).order_by("-id").first()
    if invoice is None:
        return JsonResponse({"ok": False, "error": "Purchase invoice not found."}, status=404)
    if amount > _to_float(invoice.balance_amount, 0):
        return JsonResponse(
            {"ok": False, "error": f"Payment exceeds balance. Balance: {invoice.balance_amount:.2f}"},
            status=400,
        )

    payment_no = (payload.get("payment_no") or "").strip()
    if not payment_no:
        existing = list(PurchasePayment.objects.values_list("payment_no", flat=True))
        payment_no = _next_doc_number("PAY-", existing)
    payment_date = _to_iso_or_today(payload.get("payment_date"))
    mode = (payload.get("mode") or "Cash").strip() or "Cash"
    remarks = (payload.get("remarks") or "").strip()

    with transaction.atomic():
        PurchasePayment.objects.create(
            payment_no=payment_no,
            payment_date=payment_date,
            tran_no=invoice.tran_no,
            supplier_invoice_no=invoice.supplier_invoice_no,
            supplier=invoice.supplier,
            amount=amount,
            mode=mode,
            remarks=remarks,
        )
        invoice.paid_amount = _to_float(invoice.paid_amount, 0) + amount
        invoice.balance_amount = max(_to_float(invoice.net_total, 0) - _to_float(invoice.paid_amount, 0), 0)
        if invoice.balance_amount <= 0:
            invoice.payment_status = "Paid"
            invoice.status = "Closed"
        elif invoice.paid_amount > 0:
            invoice.payment_status = "Partial"
        else:
            invoice.payment_status = "Not Paid"
        invoice.save(update_fields=["paid_amount", "balance_amount", "payment_status", "status"])

        summary = PurchaseInvoice.objects.filter(invoice_no=invoice.supplier_invoice_no).order_by("-id").first()
        if summary:
            summary.paid_amount = _to_float(summary.paid_amount, 0) + amount
            summary.save(update_fields=["paid_amount"])

        SupplierLedgerEntry.objects.create(
            supplier=invoice.supplier,
            entry_date=payment_date,
            document_type="Purchase Payment",
            document_no=payment_no,
            amount=amount,
            dr_cr="DR",
            remarks=f"Payment for invoice {invoice.supplier_invoice_no}.",
        )

    return JsonResponse(
        {
            "ok": True,
            "payment_no": payment_no,
            "tran_no": invoice.tran_no,
            "paid_amount": invoice.paid_amount,
            "balance_amount": invoice.balance_amount,
            "payment_status": invoice.payment_status,
            "status": invoice.status,
        }
    )


def login_view(request):

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            return render(request, "login.html", {"error": "Invalid login"})

    return render(request, "login.html")

def logout_view(request):
    logout(request)
    return redirect("login")
