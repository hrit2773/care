# Generated by Django 5.1.3 on 2025-01-02 20:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('emr', '0060_alter_medicationrequest_dosage_instruction'),
    ]

    operations = [
        migrations.AlterField(
            model_name='medicationrequest',
            name='dosage_instruction',
            field=models.JSONField(blank=True, default=list, null=True),
        ),
    ]
