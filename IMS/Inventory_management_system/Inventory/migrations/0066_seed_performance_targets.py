"""Seed the agreed KPI targets and default appraisal configuration."""
from django.db import migrations


# (role, sla_days, throughput_target, quality_target_pct, stage_label)
TARGETS = [
    ("Schedule Officers", 3, 20, 95, "Request created → approved/released"),
    ("Store Officers", 3, 25, 95, "Approved → materials released/dispatched"),
    ("Consultants", 1, 25, 95, "Delivered → site receipt logged"),
    ("Management", 2, 40, 95, "Order pending → approved"),
    ("Transporters", 5, 20, 95, "Dispatched → delivered"),
]


def seed(apps, schema_editor):
    RolePerformanceTarget = apps.get_model("Inventory", "RolePerformanceTarget")
    PerformanceConfig = apps.get_model("Inventory", "PerformanceConfig")

    for role, sla, throughput, quality, label in TARGETS:
        RolePerformanceTarget.objects.update_or_create(
            role=role,
            defaults={
                "sla_days": sla,
                "throughput_target": throughput,
                "quality_target_pct": quality,
                "stage_label": label,
                "active": True,
            },
        )

    PerformanceConfig.objects.update_or_create(
        pk=1,
        defaults={
            "weight_timeliness": 30,
            "weight_quality": 30,
            "weight_throughput": 20,
            "weight_responsiveness": 20,
            "min_items_for_grade": 5,
        },
    )


def unseed(apps, schema_editor):
    RolePerformanceTarget = apps.get_model("Inventory", "RolePerformanceTarget")
    RolePerformanceTarget.objects.filter(
        role__in=[t[0] for t in TARGETS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("Inventory", "0065_performanceconfig_roleperformancetarget_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
