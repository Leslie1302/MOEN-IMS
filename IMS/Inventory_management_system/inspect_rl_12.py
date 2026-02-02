
from Inventory.models import ReleaseLetter, MaterialOrder

def inspect_release_letter():
    try:
        rl = ReleaseLetter.objects.get(pk=12)
        print(f"--- Release Letter {rl.pk} ---")
        print(f"Reference Number: {rl.reference_number}")
        print(f"Title: {rl.title}")
        print(f"Status: {rl.status}")
        print(f"Total Quantity (Authorized): {rl.total_quantity}")
        print(f"Material Type: {rl.material_type}")
        print(f"Project Phase: {rl.project_phase}")
        
        # Check linked orders
        orders = MaterialOrder.objects.filter(release_letter=rl)
        total_requested = sum(o.quantity for o in orders)
        processed_count = orders.filter(status__in=['Approved', 'Partially Fulfilled', 'Fulfilled', 'Completed']).count()
        
        print(f"--- Linked Orders ---")
        print(f"Count: {orders.count()}")
        print(f"Total Requested Quantity: {total_requested}")
        print(f"Processed Orders: {processed_count}")
        
        # Check first few orders to see if they look legit
        for o in orders[:5]:
            print(f"- Order {o.request_code}: Quantity {o.quantity}, Status {o.status}")
            
    except ReleaseLetter.DoesNotExist:
        print("Release Letter 12 not found.")
    except Exception as e:
        print(f"Error: {e}")

inspect_release_letter()
