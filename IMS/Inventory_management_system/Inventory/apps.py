from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Inventory'
    
    def ready(self):
        """Import signals when app is ready"""
        import Inventory.signals
        import Inventory.release_letter_signals  # Release letter tracking signals

