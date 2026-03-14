from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_app", "0010_paymodemaster"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvoiceChargesDiscountMaster",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("charge_discount_name", models.CharField(max_length=200, unique=True)),
                ("charge_discount_type", models.CharField(max_length=50)),
                ("apply_for", models.CharField(blank=True, max_length=50)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by", models.CharField(max_length=100)),
                ("created_date", models.DateField(auto_now_add=True)),
                ("modified_date", models.DateField(auto_now=True)),
            ],
            options={
                "db_table": "invoice_charges_discounts_master",
            },
        ),
    ]

