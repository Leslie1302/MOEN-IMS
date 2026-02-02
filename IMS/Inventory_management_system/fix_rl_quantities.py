
from Inventory.models import ReleaseLetter
from decimal import Decimal

affected = ReleaseLetter.objects.filter(total_quantity=0)
count = 0
for rl in affected:
    req = rl.total_requested
    if req > 0:
        rl.total_quantity = req
        rl.save()
        count += 1
        print(f"Updated RL {rl.pk}: set quantity to {req}")
    else:
        print(f"RL {rl.pk} has no requested quantity, skipping.")

print(f"Total updated: {count}")
