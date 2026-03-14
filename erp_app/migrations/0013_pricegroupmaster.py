from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_app", "0012_stockadjustmenttypemaster"),
    ]

    operations = [
        migrations.CreateModel(
            name="PriceGroupMaster",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group_name", models.CharField(max_length=200, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by", models.CharField(max_length=100)),
                ("created_date", models.DateField(auto_now_add=True)),
                ("modified_date", models.DateField(auto_now=True)),
            ],
            options={
                "db_table": "price_group_master",
            },
        ),
    ]

