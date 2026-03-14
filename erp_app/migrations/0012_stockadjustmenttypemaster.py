from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_app", "0011_invoicechargesdiscountmaster"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockAdjustmentTypeMaster",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("adjustment_type_name", models.CharField(max_length=200, unique=True)),
                ("sort_order", models.IntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by", models.CharField(max_length=100)),
                ("created_date", models.DateField(auto_now_add=True)),
                ("modified_date", models.DateField(auto_now=True)),
            ],
            options={
                "db_table": "stock_adjustment_type_master",
            },
        ),
    ]

