"""
Seed users, groups, a transporter + vehicle, and wire up the full
request → assign → receipt → waybill-download pipeline.

Usage:
    python manage.py seed_waybill_flow
"""

from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.utils import timezone

from Inventory.models import (
    MaterialOrder, MaterialTransport, SiteReceipt, Unit, Warehouse,
)
from Inventory.transporter_models import Transporter, TransportVehicle


class Command(BaseCommand):
    help = "Add demo users, transporter, and waybill-ready assignments."

    def handle(self, *args, **opts):
        self.stdout.write("=== seed_waybill_flow ===")

        # ── 1. Users in groups ──────────────────────────────────────────
        users_spec = [
            # (username, password, group_name, is_staff)
            ("store_officer",  "pass1234", "Store Officers",   False),
            ("schedule_officer","pass1234","Schedule Officers", False),
            ("transporter_user","pass1234","Transporters",      False),
            ("consultant_user", "pass1234","Consultants",       False),
            ("manager_user",    "pass1234","Management",        True),
        ]
        created_users = {}
        for uname, pw, gname, staff in users_spec:
            user, created = User.objects.get_or_create(
                username=uname,
                defaults={"is_staff": staff, "is_active": True},
            )
            if created:
                user.set_password(pw)
                user.save()
            grp, _ = Group.objects.get_or_create(name=gname)
            user.groups.add(grp)
            created_users[uname] = user
            self.stdout.write(f"  user '{uname}' -> group '{gname}' {'(new)' if created else '(exists)'}")

        store_user = created_users["store_officer"]
        consultant = created_users["consultant_user"]

        # ── 2. Transporter + vehicle ─────────────────────────────────────
        transporter, t_created = Transporter.objects.get_or_create(
            name="FastTrack Logistics",
            defaults={
                "contact_person": "Ama Trucking",
                "phone": "+233241111111",
                "email": "info@fasttrack.test",
                "is_active": True,
                "user": created_users["transporter_user"],
            },
        )
        if t_created:
            self.stdout.write("  + Transporter 'FastTrack Logistics'")
        else:
            # ensure user link
            transporter.user = created_users["transporter_user"]
            transporter.save(update_fields=["user"])
            self.stdout.write("  ~ Transporter 'FastTrack Logistics' (exists, linked user)")

        vehicle, v_created = TransportVehicle.objects.get_or_create(
            registration_number="GR-1234-26",
            defaults={
                "transporter": transporter,
                "vehicle_type": "Truck",
                "capacity": "10 tons",
                "is_active": True,
            },
        )
        self.stdout.write(f"  {'+' if v_created else '~'} Vehicle GR-1234-26")

        # ── 3. Pick an Approved order (or create one) ────────────────────
        order = MaterialOrder.objects.filter(
            status="Approved", request_type="Release"
        ).first()

        if not order:
            unit = Unit.objects.first()
            wh = Warehouse.objects.first()
            order = MaterialOrder.objects.create(
                name="Portland Cement", code="CEM-001", unit=unit,
                warehouse=wh, quantity=Decimal("100"),
                processed_quantity=Decimal("100"),
                status="Approved", request_type="Release",
                project_type="SHEP",
                region="Greater Accra", district="Ga East",
                community="Abokobi",
                consultant="Acme Engineers Ltd",
                contractor="Beta Power Works",
                requestor=store_user.get_full_name() or store_user.username,
                user=store_user, created_by=store_user,
            )
            self.stdout.write(f"  + MaterialOrder #{order.id} (fallback)")
        else:
            self.stdout.write(f"  ~ Using existing Approved order #{order.id}: {order.name}")

        # Ensure it has processed_quantity set so transport quantity can be assigned
        if not order.processed_quantity or order.processed_quantity == 0:
            order.processed_quantity = order.quantity
            order.save(update_fields=["processed_quantity"])

        # ── 4. Assign transporter (MaterialTransport) ────────────────────
        existing_transport = MaterialTransport.objects.filter(
            material_order=order, transporter=transporter
        ).first()

        if existing_transport:
            mt = existing_transport
            self.stdout.write(f"  ~ Transport #{mt.id} already assigned")
        else:
            wb_number = f"WB-{timezone.now().strftime('%Y%m%d')}-{order.id:04d}"
            mt = MaterialTransport.objects.create(
                material_order=order,
                transporter=transporter,
                vehicle=vehicle,
                driver_name="Kwame Mensah",
                driver_phone="+233244000000",
                waybill_number=wb_number,
                quantity=order.processed_quantity or order.quantity,
                status="Loaded",
                date_dispatched=timezone.now(),
            )
            self.stdout.write(f"  + Transport #{mt.id} | waybill {wb_number}")

        # ── 5. Create SiteReceipt (required for waybill download) ─────────
        has_receipt = SiteReceipt.objects.filter(material_transport=mt).exists()
        if not has_receipt:
            SiteReceipt.objects.create(
                material_transport=mt,
                received_quantity=mt.quantity,
                received_by=consultant,
                condition="Good",
                notes="Demo receipt for waybill testing.",
            )
            self.stdout.write(f"  + SiteReceipt for Transport #{mt.id}")
        else:
            self.stdout.write(f"  ~ SiteReceipt already exists for Transport #{mt.id}")

        # ── 6. Print summary ─────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(f"""
=== Done! ===
  Login credentials:
    superuser : mac  (no password / existing)
    store     : store_officer / pass1234
    transport : transporter_user / pass1234
    consultant: consultant_user / pass1234
    manager   : manager_user / pass1234

  Waybill download URL:
    /download-waybill/{mt.id}/

  Transport status page:
    /transportation-status/

  Material orders page:
    /material-orders-officers/
"""))
