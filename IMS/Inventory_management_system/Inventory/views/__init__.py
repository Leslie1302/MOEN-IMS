from .main_views import Index, AboutView, SuperuserOnlyMixin
from .user_views import (
    ProfileView, bulk_user_upload, download_user_template, StaffProfileView
)
from .order_views import (
    RequestMaterialView, MaterialOrdersView, MaterialOrdersArchiveView, UpdateMaterialStatusView,
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
# Geospatial views temporarily commented out until djangorestframework is installed
# from .geospatial_views import (
#     ghana_map_project_sites_api, ghana_map_region_heatmap_api,
#     ghana_map_stats_api, ghana_map_districts_api, ghana_map_communities_api
# )

__all__ = [
    'Index', 'AboutView', 'SuperuserOnlyMixin',
    'ProfileView', 'bulk_user_upload', 'download_user_template', 'StaffProfileView',
    'RequestMaterialView', 'MaterialOrdersView', 'MaterialOrdersArchiveView', 'UpdateMaterialStatusView',
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
    'MaterialTransportView',
    # Geospatial API views (commented until djangorestframework is installed)
    # 'ghana_map_project_sites_api', 'ghana_map_region_heatmap_api',
    # 'ghana_map_stats_api', 'ghana_map_districts_api', 'ghana_map_communities_api'
]
