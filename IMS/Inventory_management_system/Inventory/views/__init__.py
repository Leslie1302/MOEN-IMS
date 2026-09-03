from .main_views import Index, AboutView, SuperuserOnlyMixin
from .tally_card_views import (
    TallyCardListView, TallyCardDetailView, TallyCardPDFView,
    TallyCardExcelView, tally_card_adjust,
    StockIntegrityView, TallyCardConsolidatedView,
)
from .user_views import (
    ProfileView, bulk_user_upload, download_user_template, StaffProfileView
)
from .order_views import (
    RequestMaterialView, MaterialOrdersView, MaterialOrdersArchiveView, UpdateMaterialStatusView,
    MaterialReceiptView, MaterialReceiptListView, generate_request_code,
    MaterialOrdersOfficersView, MaterialOrdersOfficersArchiveView, update_material_receipt,
    download_bulk_request_template, get_inventory_item_details,
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
    DownloadSampleTemplateView, DownloadBoQTemplateView
)
from .release_letter_views import (
    ReleaseLetterUploadView, AdjustReleaseLetterQuantityView
)
from .consultant_views import (
    ConsultantDeliveriesView, SiteReceiptCreateView, SiteReceiptListView
)
from .transport_views import MaterialTransportView
from .contract_views import ContractFulfillmentListView, ContractDetailView
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
    'MaterialOrdersOfficersView', 'MaterialOrdersOfficersArchiveView', 'update_material_receipt',
    'download_bulk_request_template', 'get_inventory_item_details',
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
    'DownloadSampleTemplateView', 'DownloadBoQTemplateView',
    'ReleaseLetterUploadView', 'AdjustReleaseLetterQuantityView',
    'ConsultantDeliveriesView', 'SiteReceiptCreateView', 'SiteReceiptListView',
    'MaterialTransportView',
    'ContractFulfillmentListView', 'ContractDetailView',
    # Geospatial API views (commented until djangorestframework is installed)
    # 'ghana_map_project_sites_api', 'ghana_map_region_heatmap_api',
    # 'ghana_map_stats_api', 'ghana_map_districts_api', 'ghana_map_communities_api'
]
