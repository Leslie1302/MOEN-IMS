from .inventory import Category, Unit, Warehouse, InventoryItem, ObsoleteMaterial
from .suppliers import (
    Supplier, SupplierPriceCatalog, SupplyContract, 
    SupplyContractItem, SupplierInvoice, SupplierInvoiceItem
)
from .orders import (
    ReleaseLetter, MaterialOrder, MaterialOrderAudit, 
    BoQOverissuanceJustification, SiteReceipt, StoreOrderAssignment
)
from .projects import Project, ProjectSite, ProjectPhase, BillOfQuantity
from .users import Profile, WeeklyReport, ReportSubmission, Notification
from .shep import SHEPCommunity
from .transport import MaterialTransport

from .utils import generate_abbreviation

# Import transporter models from the parent package's module
# Note: We use relative import ..transporter_models but since we are in 
# Inventory.models package, ..transporter_models refers to Inventory.transporter_models
from ..transporter_models import Transporter, TransportVehicle

# Export everything to make them available via 'from Inventory.models import ...'
__all__ = [
    'Category', 'Unit', 'Warehouse', 'InventoryItem', 'ObsoleteMaterial',
    'Supplier', 'SupplierPriceCatalog', 'SupplyContract', 
    'SupplyContractItem', 'SupplierInvoice', 'SupplierInvoiceItem',
    'ReleaseLetter', 'MaterialOrder', 'MaterialOrderAudit', 
    'BoQOverissuanceJustification', 'SiteReceipt', 'StoreOrderAssignment',
    'Project', 'ProjectSite', 'ProjectPhase', 'BillOfQuantity',
    'Profile', 'WeeklyReport', 'ReportSubmission', 'Notification',
    'SHEPCommunity',
    'MaterialTransport',
    'Transporter', 'TransportVehicle',
    'generate_abbreviation',
]
