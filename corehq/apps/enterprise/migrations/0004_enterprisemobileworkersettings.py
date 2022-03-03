# Generated by Django 2.2.25 on 2022-02-07 19:42

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0059_add_lite_release_management_priv'),
        ('enterprise', '0003_enterprisepermissions_modify_account'),
    ]

    operations = [
        migrations.CreateModel(
            name='EnterpriseMobileWorkerSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enable_auto_deactivation', models.BooleanField(default=False)),
                ('inactivity_period', models.IntegerField(default=90)),
                ('allow_custom_deactivation', models.BooleanField(default=False)),
                ('account', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='accounting.BillingAccount')),
            ],
        ),
    ]