from .main_views import Index, AboutView, SuperuserOnlyMixin
from .user_views import (
    ProfileView, bulk_user_upload, download_user_template, StaffProfileView
)
from .order_views import (
    RequestMaterialView, MaterialOrdersView, UpdateMaterialStatusView,
    MaterialReceiptView, MaterialReceiptListView, generate_request_code,
    MaterialOrdersOfficersView, update_material_receipt
)
from .dashboard_views import (
    consultant_dash, management_dashboard, release_letter_tracking_dashboard,
    requisition_status, get_stores_phase_label
)
from .report_views import (
    generate_weekly_report, weeklyreport_changelist,
    ReportSubmissionListView, ReportSubmissionCreateView,
    ReportSubmissionUpdateView, ReportSubmissionDetailView,
    submit_report, approve_report, reject_report
)
from .data_views import (
    UploadInventoryView, UploadCategoriesAndUnitsView, list_categories, list_units,
    get_boq_data, MaterialLegendView, MaterialHeatmapView, LowInventorySummaryView,
    BillOfQuantityView, UploadBillOfQuantityView,
    ObsoleteMaterialRegisterView, ObsoleteMaterialListView,
    ObsoleteMaterialDetailView, update_obsolete_material_status,
    DownloadSampleTemplateView
)
from .release_letter_views import (
    ReleaseLetterUploadView, AdjustReleaseLetterQuantityView
)
from .consultant_views import (
    ConsultantDeliveriesView, SiteReceiptCreateView, SiteReceiptListView
)
from .transport_views import MaterialTransportView

__all__ = [
    'Index', 'AboutView', 'SuperuserOnlyMixin',
    'ProfileView', 'bulk_user_upload', 'download_user_template', 'StaffProfileView',
    'RequestMaterialView', 'MaterialOrdersView', 'UpdateMaterialStatusView',
    'MaterialReceiptView', 'MaterialReceiptListView', 'generate_request_code',
    'MaterialOrdersOfficersView', 'update_material_receipt',
    'consultant_dash', 'management_dashboard', 'release_letter_tracking_dashboard',
    'requisition_status', 'get_stores_phase_label',
    'generate_weekly_report', 'weeklyreport_changelist',
    'ReportSubmissionListView', 'ReportSubmissionCreateView',
    'ReportSubmissionUpdateView', 'ReportSubmissionDetailView',
    'submit_report', 'approve_report', 'reject_report',
    'UploadInventoryView', 'UploadCategoriesAndUnitsView', 'list_categories', 'list_units',
    'get_boq_data', 'MaterialLegendView', 'MaterialHeatmapView', 'LowInventorySummaryView',
    'BillOfQuantityView', 'UploadBillOfQuantityView',
    'ObsoleteMaterialRegisterView', 'ObsoleteMaterialListView',
    'ObsoleteMaterialDetailView', 'update_obsolete_material_status',
    'DownloadSampleTemplateView',
    'ReleaseLetterUploadView', 'AdjustReleaseLetterQuantityView',
    'ConsultantDeliveriesView', 'SiteReceiptCreateView', 'SiteReceiptListView',
    'MaterialTransportView'
]
