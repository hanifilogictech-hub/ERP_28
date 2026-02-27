from datetime import date, timedelta

from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce

from ..charting import build_chart, month_range
from ..db import init_db
from ..models import (
    GoodsReceipt,
    GoodsReceiptItem,
    GoodsReturn,
    GoodsReturnItem,
    Product,
    PurchaseInvoice,
    PurchaseInvoiceEntry,
    PurchaseOrder,
    SalesInvoice,
    SalesOrder,
    SalesOrderItem,
    StockAdjustment,
    StockAdjustmentItem,
    StockRequest,
    StockRequestItem,
    StockTake,
    StockTransfer,
    StockTransferItem,
)


def _sum_amount(queryset, field):
    return queryset.aggregate(v=Sum(field))["v"] or 0


def _date_text(value):
    return value.strftime("%d-%m-%Y")


def dashboard_data():
    init_db()
    today = date.today()
    yesterday = today - timedelta(days=1)
    start_week = today - timedelta(days=today.weekday())

    total_sales_today = _sum_amount(
        SalesInvoice.objects.filter(invoice_date=today), "total_amount"
    )
    sold_yesterday = _sum_amount(
        SalesInvoice.objects.filter(invoice_date=yesterday), "total_amount"
    )
    pi_base = PurchaseInvoiceEntry.objects.all()
    purchases_today = _sum_amount(
        PurchaseInvoiceEntry.objects.filter(invoice_date=today), "net_total"
    )
    if not purchases_today:
        purchases_today = _sum_amount(
            PurchaseInvoice.objects.filter(invoice_date=today), "total_amount"
        )
    sales_total = _sum_amount(SalesInvoice.objects.all(), "total_amount")
    sales_paid = _sum_amount(SalesInvoice.objects.all(), "paid_amount")
    purchase_total = _sum_amount(pi_base, "net_total")
    purchase_paid = _sum_amount(pi_base, "paid_amount")
    if purchase_total == 0 and purchase_paid == 0:
        purchase_total = _sum_amount(PurchaseInvoice.objects.all(), "total_amount")
        purchase_paid = _sum_amount(PurchaseInvoice.objects.all(), "paid_amount")
    due_amount = max(sales_total - sales_paid, 0)
    profit_total = sales_total - purchase_total
    stock_value = (
        Product.objects.aggregate(v=Coalesce(Sum(F("stock_qty") * F("cost_price")), 0.0))["v"]
        or 0
    )

    this_month_start, this_month_end = month_range(today, 0)
    prev_month_start, prev_month_end = month_range(today, 1)
    this_month_sales = _sum_amount(
        SalesInvoice.objects.filter(invoice_date__range=(this_month_start, this_month_end)),
        "total_amount",
    )
    prev_month_sales = _sum_amount(
        SalesInvoice.objects.filter(invoice_date__range=(prev_month_start, prev_month_end)),
        "total_amount",
    )
    growth_note = (
        "Business is growing" if this_month_sales >= prev_month_sales else "Watch revenue trend"
    )

    recent_purchase_orders = [
        {
            "order_no": row["order_no"],
            "order_date": _date_text(row["order_date"]),
            "invoice_no": row["invoice_no"],
            "supplier": row["supplier"],
            "amount": row["amount"],
        }
        for row in PurchaseOrder.objects.order_by("-order_date", "-id").values(
            "order_no", "order_date", "invoice_no", "supplier", "amount"
        )[:5]
    ]
    recent_sales_orders = [
        {
            "order_no": row["order_no"],
            "order_date": _date_text(row["order_date"]),
            "invoice_no": row["invoice_no"],
            "customer": row["customer"],
            "amount": row["amount"],
        }
        for row in SalesOrder.objects.order_by("-order_date", "-id").values(
            "order_no", "order_date", "invoice_no", "customer", "amount"
        )[:5]
    ]
    recent_purchase_invoices = [
        {
            "invoice_no": row["supplier_invoice_no"],
            "invoice_date": _date_text(row["invoice_date"]),
            "supplier": row["supplier"],
            "total_amount": row["net_total"],
        }
        for row in PurchaseInvoiceEntry.objects.order_by("-invoice_date", "-id").values(
            "supplier_invoice_no", "invoice_date", "supplier", "net_total"
        )[:5]
    ]
    if not recent_purchase_invoices:
        recent_purchase_invoices = [
            {
                "invoice_no": row["invoice_no"],
                "invoice_date": _date_text(row["invoice_date"]),
                "supplier": row["supplier"],
                "total_amount": row["total_amount"],
            }
            for row in PurchaseInvoice.objects.order_by("-invoice_date", "-id").values(
                "invoice_no", "invoice_date", "supplier", "total_amount"
            )[:5]
        ]
    recent_sales_invoices = [
        {
            "invoice_no": row["invoice_no"],
            "invoice_date": _date_text(row["invoice_date"]),
            "customer": row["customer"],
            "total_amount": row["total_amount"],
        }
        for row in SalesInvoice.objects.order_by("-invoice_date", "-id").values(
            "invoice_no", "invoice_date", "customer", "total_amount"
        )[:5]
    ]

    recent_goods_receipts = [
        {
            "gr_no": row["gr_no"],
            "receipt_date": _date_text(row["receipt_date"]),
            "supplier": row["supplier"],
            "location": row["location"],
            "items_count": row["items_count"],
        }
        for row in GoodsReceipt.objects.order_by("-receipt_date", "-id")
        .annotate(items_count=Count("items"))
        .values("gr_no", "receipt_date", "supplier", "location", "items_count")[:5]
    ]

    recent_goods_returns = [
        {
            "return_no": row["return_no"],
            "return_date": _date_text(row["return_date"]),
            "supplier": row["supplier"],
            "status": row["status"],
            "total_amount": row["total_amount"],
        }
        for row in GoodsReturn.objects.order_by("-return_date", "-id").values(
            "return_no", "return_date", "supplier", "status", "total_amount"
        )[:5]
    ]

    recent_stock_requests = [
        {
            "request_no": row["request_no"],
            "request_date": _date_text(row["request_date"]),
            "from_location": row["from_location"],
            "to_location": row["to_location"],
            "status": row["status"],
            "remarks": row["remarks"],
        }
        for row in StockRequest.objects.order_by("-request_date", "-id").values(
            "request_no",
            "request_date",
            "from_location",
            "to_location",
            "status",
            "remarks",
        )[:5]
    ]

    recent_stock_transfers = [
        {
            "transfer_no": row["transfer_no"],
            "transfer_date": _date_text(row["transfer_date"]),
            "from_location": row["from_location"],
            "to_location": row["to_location"],
            "status": row["status"],
            "remarks": row["remarks"],
        }
        for row in StockTransfer.objects.order_by("-transfer_date", "-id").values(
            "transfer_no",
            "transfer_date",
            "from_location",
            "to_location",
            "status",
            "remarks",
        )[:5]
    ]

    recent_stock_adjustments = [
        {
            "adjustment_no": row["adjustment_no"],
            "adjustment_date": _date_text(row["adjustment_date"]),
            "location": row["location"],
            "remarks": row["remarks"],
            "created_by": row["created_by"],
        }
        for row in StockAdjustment.objects.order_by("-adjustment_date", "-id").values(
            "adjustment_no",
            "adjustment_date",
            "location",
            "remarks",
            "created_by",
        )[:5]
    ]

    recent_stock_takes = [
        {
            "stock_take_no": row["stock_take_no"],
            "stock_take_date": _date_text(row["stock_take_date"]),
            "location": row["location"],
            "status": row["status"],
            "remarks": row["remarks"],
            "user_name": row["user_name"],
        }
        for row in StockTake.objects.order_by("-stock_take_date", "-id").values(
            "stock_take_no",
            "stock_take_date",
            "location",
            "status",
            "remarks",
            "user_name",
        )[:5]
    ]

    received_qty_total = _sum_amount(GoodsReceiptItem.objects.all(), "received_qty")
    returned_qty_total = _sum_amount(GoodsReturnItem.objects.all(), "quantity")
    retained_qty_total = max(received_qty_total - returned_qty_total, 0)
    requested_qty_total = _sum_amount(StockRequestItem.objects.all(), "total_qty")
    transferred_qty_total = _sum_amount(StockTransferItem.objects.all(), "qty")
    adjustment_minus = _sum_amount(
        StockAdjustmentItem.objects.filter(adjustment_sign="-"), "adjustment_qty"
    )
    adjustment_plus = _sum_amount(
        StockAdjustmentItem.objects.filter(adjustment_sign="+"), "adjustment_qty"
    )

    weekly_sales = []
    for i in range(7):
        d = start_week + timedelta(days=i)
        d_prev = d - timedelta(days=7)
        cur_val = _sum_amount(SalesInvoice.objects.filter(invoice_date=d), "total_amount")
        prev_val = _sum_amount(SalesInvoice.objects.filter(invoice_date=d_prev), "total_amount")
        weekly_sales.append(
            {
                "day": d.strftime("%A"),
                "current": cur_val,
                "last": prev_val,
                "diff": cur_val - prev_val,
            }
        )

    week_labels, week_values = [], []
    for i in range(11, -1, -1):
        ws = start_week - timedelta(weeks=i)
        we = ws + timedelta(days=6)
        val = _sum_amount(
            SalesInvoice.objects.filter(invoice_date__range=(ws, we)), "total_amount"
        )
        week_labels.append(f"W{ws.isocalendar().week}")
        week_values.append(val)

    month_labels, month_values = [], []
    for i in range(11, -1, -1):
        ms, me = month_range(today, i)
        val = _sum_amount(
            SalesInvoice.objects.filter(invoice_date__range=(ms, me)), "total_amount"
        )
        month_labels.append(ms.strftime("%b %Y"))
        month_values.append(val)

    day_labels, day_values, profit_labels, profit_values = [], [], [], []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        sales_val = _sum_amount(SalesInvoice.objects.filter(invoice_date=d), "total_amount")
        purch_val = _sum_amount(PurchaseInvoiceEntry.objects.filter(invoice_date=d), "net_total")
        if not purch_val:
            purch_val = _sum_amount(PurchaseInvoice.objects.filter(invoice_date=d), "total_amount")
        day_labels.append(d.strftime("%a %m/%d"))
        day_values.append(sales_val)
        profit_labels.append(d.strftime("%a %m/%d"))
        profit_values.append(max(sales_val - purch_val, 0))

    total_bills = SalesInvoice.objects.aggregate(v=Count("id"))["v"] or 0
    total_items = _sum_amount(SalesOrderItem.objects.all(), "qty")
    total_cost = (
        SalesOrderItem.objects.aggregate(v=Coalesce(Sum(F("qty") * F("product__cost_price")), 0.0))[
            "v"
        ]
        or 0
    )
    analysis_profit = sales_total - total_cost
    avg_bill = sales_total / total_bills if total_bills else 0
    margin = (analysis_profit / sales_total * 100) if sales_total else 0

    department_sales = list(
        SalesOrderItem.objects.values(name=F("product__department"))
        .annotate(amount=Coalesce(Sum("amount"), 0.0))
        .order_by("-amount")
    )
    category_sales = list(
        SalesOrderItem.objects.values(name=F("product__category"))
        .annotate(amount=Coalesce(Sum("amount"), 0.0))
        .order_by("-amount")
    )
    popular_products = list(
        SalesOrderItem.objects.values(product_name=F("product__product_name"))
        .annotate(sold_qty=Coalesce(Sum("qty"), 0), amount=Coalesce(Sum("amount"), 0.0))
        .order_by("-sold_qty")[:8]
    )
    minimum_qty = list(
        Product.objects.filter(stock_qty__lte=F("reorder_qty"))
        .annotate(balance_value=F("stock_qty") * F("cost_price"))
        .values("product_name", "stock_qty", "reorder_qty", "balance_value")
        .order_by("stock_qty")
    )
    salesman_performance = list(
        SalesOrder.objects.values("salesman")
        .annotate(amount=Coalesce(Sum("amount"), 0.0))
        .order_by("-amount")
    )

    return {
        "today_display": today.strftime("%d/%m/%Y"),
        "total_sales_today": total_sales_today,
        "sold_yesterday": sold_yesterday,
        "purchases_today": purchases_today,
        "due_amount": due_amount,
        "stock_value": stock_value,
        "profit_total": profit_total,
        "growth_note": growth_note,
        "recent_purchase_orders": recent_purchase_orders,
        "recent_sales_orders": recent_sales_orders,
        "recent_purchase_invoices": recent_purchase_invoices,
        "recent_goods_receipts": recent_goods_receipts,
        "recent_goods_returns": recent_goods_returns,
        "recent_stock_requests": recent_stock_requests,
        "recent_stock_transfers": recent_stock_transfers,
        "recent_stock_adjustments": recent_stock_adjustments,
        "recent_stock_takes": recent_stock_takes,
        "recent_sales_invoices": recent_sales_invoices,
        "purchase_flow": {
            "received_qty_total": received_qty_total,
            "returned_qty_total": returned_qty_total,
            "retained_qty_total": retained_qty_total,
        },
        "stock_flow": {
            "requested_qty_total": requested_qty_total,
            "transferred_qty_total": transferred_qty_total,
            "adjustment_minus_total": adjustment_minus,
            "adjustment_plus_total": adjustment_plus,
        },
        "stock_status": {
            "pending_requests": StockRequest.objects.filter(status__in=["Draft", "Pending Approval", "Submitted"]).count(),
            "sent_transfers": StockTransfer.objects.filter(status="Sent").count(),
            "pending_stock_takes": StockTake.objects.filter(status="Pending").count(),
        },
        "purchase_status": {
            "total": purchase_total,
            "paid": purchase_paid,
            "due": max(purchase_total - purchase_paid, 0),
        },
        "sales_status": {
            "total": sales_total,
            "paid": sales_paid,
            "due": max(sales_total - sales_paid, 0),
        },
        "weekly_sales": weekly_sales,
        "sales_30d": build_chart(day_labels, day_values),
        "sales_12w": build_chart(week_labels, week_values),
        "sales_12m": build_chart(month_labels, month_values),
        "profit_30d": build_chart(profit_labels, profit_values),
        "sales_analysis": {
            "total_sales": sales_total,
            "total_bills": total_bills,
            "total_items": total_items,
            "avg_bill": avg_bill,
            "total_cost": total_cost,
            "profit": analysis_profit,
            "margin": margin,
        },
        "department_sales": department_sales,
        "category_sales": category_sales,
        "popular_products": popular_products,
        "minimum_qty": minimum_qty,
        "salesman_performance": salesman_performance,
    }
