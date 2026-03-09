"""
Forms package — split from a single 1443-line forms.py into domain-based modules.

All forms are re-exported here so existing ``from Inventory.forms import X``
and ``from .forms import X`` imports continue to work unchanged.
"""

# Auth & user profile
from .auth import (  # noqa: F401
    AuthenticationForm,
    UserRegistration,
    UserUpdateForm,
    ProfileUpdateForm,
    PasswordChangeForm,
    ExcelUploadForm,
)

# Material orders, receipts, reports, release letters
from .orders import (  # noqa: F401
    InventoryItemForm,
    InventoryItemFormSet,
    MaterialOrderForm,
    MaterialOrderFormSet,
    BulkMaterialRequestForm,
    MaterialReceiptForm,
    MaterialReceiptFormSet,
    ReportSubmissionForm,
    ReleaseLetterUploadForm,
)

# Transport management
from .transport import (  # noqa: F401
    TransporterForm,
    TransportVehicleForm,
    TransportAssignmentForm,
    TransporterImportForm,
    MaterialTransportForm,
)

# Projects, BOQ, site receipts, obsolete materials
from .projects import (  # noqa: F401
    ProjectForm,
    SiteReceiptForm,
    BoQOverissuanceJustificationForm,
    BillOfQuantityForm,
    BillOfQuantityFormSet,
    ObsoleteMaterialForm,
)

# Supply chain (suppliers, contracts, invoices)
from .supply import (  # noqa: F401
    SupplierForm,
    SupplierPriceCatalogForm,
    BulkPriceCatalogUploadForm,
    SupplyContractForm,
    SupplyContractItemForm,
    SupplyContractItemFormSet,
    SupplierInvoiceForm,
    SupplierInvoiceItemForm,
    SupplierInvoiceItemFormSet,
    InvoiceVerificationForm,
    InvoiceApprovalForm,
)

# Admin & bulk imports
from .admin import (  # noqa: F401
    BulkUserUploadForm,
    ExcelUserImportForm,
    SHEPCommunityForm,
    ExcelProjectSiteImportForm,
)
