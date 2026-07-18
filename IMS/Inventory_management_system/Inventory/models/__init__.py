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
from .shep import Community, SHEPCommunity  # SHEPCommunity is a back-compat alias for Community
from .transport import MaterialTransport
from .project_type import ProjectType
from .people import MemberOfParliament, ProjectConsultant
from .signatory import Signatory
from .geography import Region, District, Package  # Geospatial models (Phase 2)
from .access_rate import MeterInstallation, AccessRateConfig, RegionPopulation  # Track B (access rate map)
from .performance import (  # Rebuilt KPI / appraisal system
    RolePerformanceTarget, PerformanceConfig, PerformanceSnapshot,
    GRADABLE_ROLES, GRADE_BANDS,
)

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
    'Community', 'SHEPCommunity',
    'MaterialTransport',
    'Transporter', 'TransportVehicle',
    'ProjectType',
    'MemberOfParliament', 'ProjectConsultant',
    'Signatory',
    'Region', 'District', 'Package',  # Geospatial models
    'MeterInstallation', 'AccessRateConfig', 'RegionPopulation',  # Access rate models
    'RolePerformanceTarget', 'PerformanceConfig', 'PerformanceSnapshot',  # KPI system
    'GRADABLE_ROLES', 'GRADE_BANDS',
    'generate_abbreviation',
]
