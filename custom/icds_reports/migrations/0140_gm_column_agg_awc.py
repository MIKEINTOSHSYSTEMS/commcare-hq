# Generated by Django 1.11.16 on 2019-10-28

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('icds_reports', '0138_update_thr_view'),
    ]

    operations = [
        migrations.RunSQL("ALTER table agg_awc ADD COLUMN awc_with_gm_devices INTEGER")
    ]
