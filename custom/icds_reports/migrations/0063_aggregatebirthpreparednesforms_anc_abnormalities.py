# Generated by Django 1.11.14 on 2018-08-27 07:40
from corehq.sql_db.operations import RawSQLMigration
from django.db import migrations, models

from custom.icds_reports.const import SQL_TEMPLATES_ROOT

migrator = RawSQLMigration((SQL_TEMPLATES_ROOT,))


class Migration(migrations.Migration):

    dependencies = [
        ('icds_reports', '0062_disha_indicators_create_view'),
    ]

    operations = [
        migrations.AddField(
            model_name='aggregatebirthpreparednesforms',
            name='anc_abnormalities',
            field=models.PositiveSmallIntegerField(
                help_text="Last value of anc_details/anc_abnormalities = 'yes'", null=True
            ),
        ),
        migrator.get_migration('update_tables26.sql'),
    ]
