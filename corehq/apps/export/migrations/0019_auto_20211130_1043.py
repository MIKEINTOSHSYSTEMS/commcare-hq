# Generated by Django 2.2.24 on 2021-11-30 10:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('export', '0013_googleapitoken'),
    ]

    operations = [
        migrations.AlterField(
            model_name='googleapitoken',
            name='token',
            field=models.CharField(max_length=700),
        ),
    ]