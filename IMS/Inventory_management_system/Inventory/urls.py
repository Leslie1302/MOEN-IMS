from django.urls import path, include, reverse_lazy
from django.conf import settings
from django.conf.urls import handler403, handler404, handler500
from django.views.generic.base import RedirectView
# Password reset routes removed — authentication is handled exclusively via Microsoft 365 OAuth.

# Import views from their respective modules
from .views import (
    Index, RequestMaterialView, MaterialOrdersView, UpdateMaterialStatusView,
    ProfileView, UploadInventoryView, UploadCategoriesAndUnitsView, list_categories,
    list_units, get_boq_data, MaterialHeatmapView, MaterialLegendView, LowInventorySummaryView,
    TallyCardListView, TallyCardDetailView, TallyCardPDFView,
    TallyCardExcelView, tally_card_adjust,
    StockIntegrityView, TallyCardConsolidatedView,
    BillOfQuantityView, UploadBillOfQuantityView, consultant_dash, management_dashboard,
    MaterialReceiptView, update_material_receipt, ReportSubmissionListView,
    ReportSubmissionCreateView, ReportSubmissionDetailView, ReportSubmissionUpdateView,
    submit_report, approve_report, reject_report, MaterialTransportView, ReleaseLetterUploadView,
    AdjustReleaseLetterQuantityView,
    StaffProfileView, MaterialOrdersOfficersView, MaterialOrdersOfficersArchiveView, MaterialOrdersArchiveView, DownloadSampleTemplateView, DownloadBoQTemplateView, download_bulk_request_template,
    generate_weekly_report, weeklyreport_changelist, bulk_user_upload,
    ObsoleteMaterialRegisterView, ObsoleteMaterialListView, ObsoleteMaterialDetailView,
    update_obsolete_material_status, release_letter_tracking_dashboard,
    AdjustReleaseLetterQuantityView, AboutView, requisition_status,
    get_inventory_item_details,
    # Geospatial API views (Phase 2) - commented until djangorestframework is installed
    # ghana_map_project_sites_api, ghana_map_region_heatmap_api,
    # ghana_map_stats_api, ghana_map_districts_api, ghana_map_communities_api,
)
from .views.map_views import ghana_map_view, ghana_map_data_api
from .views.meter_views import (
    meter_install_create, meter_install_list,
    verify_meter_installation, meter_install_bulk_upload,
    meter_install_bulk_errors_csv,
)
from .views.site_progress_views import (
    site_progress_list, site_progress_edit, site_progress_api,
)
from .views.geospatial_views import (
    ghana_map_project_sites_api, ghana_map_region_heatmap_api,
    ghana_map_stats_api, ghana_map_districts_api, ghana_map_communities_api
)
from .views.kpi_views import (
    StaffProfilePerformanceView, ManagementDashboardKPIView,
    staff_performance_api, management_dashboard_kpi_api
)
from .views.performance_views import (
    MyPerformanceView, TeamPerformanceView, staff_performance_detail,
)

# Import project management views
from .project_management_views import (
    ProjectManagementDashboardView,
    CommunityAnalysisView,
    PackageAnalysisView,
    MaterialAnalysisView,
    CommunityProgressListView,
    CommunityProgressBreakdownView,
    PullTargetsFromBoqView,
    BulkPullTargetsFromBoqView
)

# Import project creation and assignment views
from .views.project_views import (
    ProjectListView, ProjectCreateView, ProjectDetailView, ProjectUpdateView,
    project_assignment_view, project_site_create_view
)

# Import transporter views
from . import transporter_views
from .transporter_views import (
    TransporterListView, TransporterDetailView, TransporterCreateView, TransporterUpdateView, TransporterDeleteView,
    TransportVehicleListView, TransportVehicleDetailView, TransportVehicleCreateView, TransportVehicleUpdateView, TransportVehicleDeleteView,
    TransporterAssignmentView, TransporterLegendView, import_transporters, export_transporters_template, ajax_load_vehicles,
    TransportationStatusView, update_transport_status,
    ReleaseLetterListView,
)

# Import help view
from .views_help import HelpView

# Import auth views
from .auth_views import SignUpView, SignInView, CustomLogoutView, Dashboard
from .views_auth import AwaitingAuthorizationView, custom_403_view, custom_404_view, custom_500_view

# Import 2FA views
from .views_2fa import (
    setup_2fa, setup_2fa_qr, confirm_2fa, disable_2fa,
    backup_codes, regenerate_backup_codes, verify_2fa
)

# Import item views
from .item_views import AddItem, EditItem, DeleteItem

# Import consultant views
from .views import ConsultantDeliveriesView, SiteReceiptCreateView, SiteReceiptListView

# Import notification views
from .notification_views import (
    NotificationListView, notification_detail, mark_notification_read,
    mark_all_notifications_read, get_unread_count, delete_notification,
    notification_preferences
)

# Import BoQ overissuance views
from .boq_overissuance_views import (
    PackageReconciliationView,
    BoQOverissuanceSummaryView, BoQOverissuanceJustificationCreateView,
    BoQOverissuanceJustificationListView, BoQOverissuanceJustificationDetailView,
    review_overissuance_justification, boq_overissuance_stats
)

# Import BOQ management views
from .boq_views import BulkEditBOQView, SingleEditBOQView
from .boq_community_views import (
    CommunityBOQBulkEditView, CommunityListAPIView, 
    CommunityBOQDataAPIView, BulkUpdateBOQAPIView
)

# Import signature views
from .signature_lookup_view import signature_lookup, signature_verify, signature_api_lookup


# Import stores management views
from .stores_management_views import (
    PendingOrdersView, AssignedOrdersView, AssignOrderView,
    MyAssignedOrdersView, update_assignment_status, bulk_assign_orders,
    StoreOfficerPerformanceDashboard,
    process_order_partial
)

# Import SHEP community management views
from .shep_community_views import (
    SHEPCommunityListView, SHEPCommunityCreateView, SHEPCommunityUpdateView,
    SHEPCommunityDeleteView, AbbreviationLegendView,
    get_districts_by_region, get_communities_by_district,
    get_packages_by_community, generate_auto_package_number,
    get_mps_by_constituency, stock_for_item, inventory_stock_api, community_detail_api,
    download_material_template, download_shep_community_template,
    download_community_template, download_mp_template,
    download_consultant_template,
    upload_communities, upload_members_of_parliament,
    upload_project_consultants,
    upload_shep_communities,
)

# Phase C: two-step Material Request flow
from .views.request_flow_views import (
    SelectProjectView, RequestMaterialForProjectView,
    resolve_consignee_for_community,
    download_request_template, upload_requests,
)

# Phase F: release-side document workflow
from .views.release_document_views import (
    ReleaseLetterDetailView, GenerateReleaseDocumentsView,
    CreateReleaseLetterFromRequestView,
    UploadSignedScanView, ConfirmSignedScanView, MarkReleasedView,
    AdjustReleaseDocumentsView, MemoPreviewView, LetterPreviewView,
    SaveDocumentHtmlView, RevertDocumentHtmlView, SendReleaseDocumentsView,
    SignDocumentView, RebuildSignedDocumentView, SendForSignatureView,
    ReconciliationReportView, BoQAssistanceView,
)
from .views.letterhead_views import LetterheadSettingsView
from .views.verify_views import VerifyDocumentView
from .views.approval_views import (
    ApprovalQueueView, CallOfficerView, DeclareUrgentView, SigningPageView,
    UrgentReleasesReportView,
)
from .views.archive_views import (
    ArchiveListView, ArchiveDetailView, ArchiveCreateView,
    ArchiveBulkImportView, ArchiveTemplateView, ArchiveImportErrorsView,
)

# Error handlers
handler403 = custom_403_view
handler404 = custom_404_view
handler500 = custom_500_view

urlpatterns = [
    # Public routes
    path('', Index.as_view(), name='index'),
    path('about/', AboutView.as_view(), name='about'),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('signin/', SignInView.as_view(), name='signin'),
    path('logout/', CustomLogoutView.as_view(template_name='Inventory/logout.html'), name='logout'),
    path('awaiting-authorization/', AwaitingAuthorizationView.as_view(), name='awaiting_authorization'),
    path('help/', HelpView.as_view(), name='help'),
    
    # Password reset routes removed — M365 handles password recovery
    # for all company accounts. Superuser access is available via Django admin.
    
    # Two-Factor Authentication URLs (for reference; MFA is enforced via Azure AD)
    path('2fa/setup/', setup_2fa, name='setup_2fa'),
    path('2fa/setup/qr/', setup_2fa_qr, name='2fa_qr'),
    path('2fa/confirm/', confirm_2fa, name='confirm_2fa'),
    path('2fa/verify/', verify_2fa, name='verify_2fa'),
    path('2fa/disable/', disable_2fa, name='disable_2fa'),
    path('2fa/backup-codes/', backup_codes, name='2fa_backup_codes'),
    path('2fa/regenerate-backup-codes/', regenerate_backup_codes, name='regenerate_backup_codes'),
    
    # Authenticated routes
    path('dashboard/', Dashboard.as_view(), name='dashboard'),
    path('add-item', AddItem.as_view(), name='add-item'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('staff-profile/<str:username>/', StaffProfileView.as_view(), name='staff_profile'),
    path('staff-profile/<str:username>/performance/', StaffProfilePerformanceView.as_view(), name='staff_profile_performance'),
    # Phase C: the two-step flow IS now /request-material/. The legacy
    # single-page RequestMaterialView is preserved at /request-material/legacy/
    # for emergency fallback during the transition; remove that route after
    # one stable production cycle.
    path('request-material/', SelectProjectView.as_view(), name='request_material'),
    # Alias name used by the Step 2 template ({% url 'request_material_select' %}).
    path('request-material/', SelectProjectView.as_view(), name='request_material_select'),
    path('request-material/legacy/', RequestMaterialView.as_view(), name='request_material_legacy'),
    path('request-material/bulk-template/', download_bulk_request_template, name='download_bulk_request_template'),

    # Phase C: routes for the two-step Material Request flow. These views
    # were imported above but never registered, which caused NoReverseMatch
    # on {% url 'download_request_template' %} in the Step 1 page.
    path('request-material/start/<str:project_code>/', RequestMaterialForProjectView.as_view(), name='request_material_for_project'),
    path('request-material/template/', download_request_template, name='download_request_template'),
    path('request-material/upload/', upload_requests, name='upload_requests'),
    path('api/resolve-consignee/', resolve_consignee_for_community, name='api_resolve_consignee'),
    path('material-orders/', MaterialOrdersView.as_view(), name='material_orders'),
    path('material-orders/archive/', MaterialOrdersArchiveView.as_view(), name='material_orders_archive'),
    path('material-orders-officers/', MaterialOrdersOfficersView.as_view(), name='material_orders_officers'),
    path('material-orders-officers/archive/', MaterialOrdersOfficersArchiveView.as_view(), name='material_orders_officers_archive'),
    path('requisition-status/', requisition_status, name='requisition_status'),
    # Parameterized routes
    path('update_material_status/<int:order_id>/<str:new_status>/', UpdateMaterialStatusView.as_view(), name='update_material_status'),
    path('delete-item/<int:pk>', DeleteItem.as_view(), name='delete-item'),
    path('edit-item/<int:pk>', EditItem.as_view(), name='edit-item'),
    path('upload-inventory/', UploadInventoryView.as_view(), name='upload_inventory'),
    path('download-sample-template/', DownloadSampleTemplateView.as_view(), name='download_sample_template'),
    path('download-boq-template/', DownloadBoQTemplateView.as_view(), name='download_boq_template'),
    path('list-categories/', list_categories, name='list_categories'),
    path('list-units/', list_units, name='list_units'),
    path('get-boq-data/', get_boq_data, name='get_boq_data'),
    path('upload-categories-units/', UploadCategoriesAndUnitsView.as_view(), name='upload_categories_units'),
    path('receive-material/', MaterialReceiptView.as_view(), name='material_receipt'),
    path('api/inventory-item/<int:item_id>/', get_inventory_item_details, name='get_inventory_item_details'),
    path('material-heatmap/', MaterialHeatmapView.as_view(), name='material_heatmap'),
    path('material-legend/', MaterialLegendView.as_view(), name='material_legend'),
    path('low-inventory-summary/', LowInventorySummaryView.as_view(), name='low_inventory_summary'),
    path('bill-of-quantity/', BillOfQuantityView.as_view(), name='bill_of_quantity'),
    path('upload-bill-of-quantity/', UploadBillOfQuantityView.as_view(), name='upload_bill_of_quantity'),
    path('bill-of-quantity/bulk-edit/', BulkEditBOQView.as_view(), name='boq_bulk_edit'),
    path('bill-of-quantity/<int:pk>/edit/', SingleEditBOQView.as_view(), name='boq_single_edit'),
    
    # Community-based BOQ bulk edit
    path('bill-of-quantity/community-bulk-edit/', CommunityBOQBulkEditView.as_view(), name='boq_community_bulk_edit'),
    path('bill-of-quantity/api/communities/', CommunityListAPIView.as_view(), name='community_list_api'),
    path('bill-of-quantity/api/community-data/', CommunityBOQDataAPIView.as_view(), name='community_boq_data_api'),
    path('bill-of-quantity/api/bulk-update/', BulkUpdateBOQAPIView.as_view(), name='bulk_update_boq_api'),
    path('consultant_dash/', consultant_dash, name='consultant_dash'),
    path('management_dashboard/', management_dashboard, name='management_dashboard'),
    path('management-dashboard-kpi/', ManagementDashboardKPIView.as_view(), name='management_dashboard_kpi'),
    # Rebuilt KPI / appraisal system
    path('performance/me/', MyPerformanceView.as_view(), name='my_performance'),
    path('performance/team/', TeamPerformanceView.as_view(), name='team_performance'),
    path('performance/user/<str:username>/', staff_performance_detail, name='staff_performance_detail'),
    path('project-management-dashboard/', ProjectManagementDashboardView.as_view(), name='project_management_dashboard'),
    path('ghana-map/', ghana_map_view, name='ghana_map'),
    path('ghana-map-total-sites/', lambda request: __import__('django.views.generic', fromlist=['TemplateView']).TemplateView.as_view(template_name='Inventory/ghana_map_total_sites.html')(request), name='ghana_map_total_sites'),
    path('ghana-map-completed-sites/', lambda request: __import__('django.views.generic', fromlist=['TemplateView']).TemplateView.as_view(template_name='Inventory/ghana_map_completed_sites.html')(request), name='ghana_map_completed_sites'),
    path('ghana-map-active-sites/', lambda request: __import__('django.views.generic', fromlist=['TemplateView']).TemplateView.as_view(template_name='Inventory/ghana_map_active_sites.html')(request), name='ghana_map_active_sites'),
    path('ghana-map-progress/', lambda request: __import__('django.views.generic', fromlist=['TemplateView']).TemplateView.as_view(template_name='Inventory/ghana_map_progress.html')(request), name='ghana_map_progress'),
    path('api/ghana-map-data/', ghana_map_data_api, name='ghana_map_data_api'),

    # Access-rate / meter installations (Track B Phase B5).
    path('access-rate/meters/',           meter_install_list,            name='meter_install_list'),
    path('access-rate/meters/new/',       meter_install_create,          name='meter_install_create'),
    path('access-rate/meters/bulk/',      meter_install_bulk_upload,     name='meter_install_bulk_upload'),
    path('access-rate/meters/bulk/errors/', meter_install_bulk_errors_csv, name='meter_install_bulk_errors_csv'),
    path('access-rate/meters/<int:pk>/verify/', verify_meter_installation, name='meter_install_verify'),

    # Site progress (consultant-driven; interim source for map headline).
    path('site-progress/',               site_progress_list, name='site_progress_list'),
    path('site-progress/<int:pk>/edit/', site_progress_edit, name='site_progress_edit'),
    path('api/site-progress/',           site_progress_api,  name='site_progress_api'),
    path('api/inventory-stock/', inventory_stock_api, name='inventory_stock_api'),
    path('api/community-detail/', community_detail_api, name='community_detail_api'),
    path('api/staff-performance/', staff_performance_api, name='staff_performance_api'),
    path('api/management-dashboard-kpi/', management_dashboard_kpi_api, name='management_dashboard_kpi_api'),
    path('project-analysis/community/', CommunityAnalysisView.as_view(), name='project_community_analysis'),
    path('project-analysis/community-progress/', CommunityProgressListView.as_view(), name='community_progress_list'),
    path('project-analysis/community-progress/breakdown/', CommunityProgressBreakdownView.as_view(), name='community_progress_breakdown'),
    path('project-analysis/community-progress/pull-targets/', PullTargetsFromBoqView.as_view(), name='pull_targets_from_boq'),
    path('project-analysis/community-progress/pull-targets-all/', BulkPullTargetsFromBoqView.as_view(), name='bulk_pull_targets_from_boq'),
    path('project-analysis/package/', PackageAnalysisView.as_view(), name='project_package_analysis'),
    path('project-analysis/material/', MaterialAnalysisView.as_view(), name='project_material_analysis'),

    # Project creation and management
    path('projects/', ProjectListView.as_view(), name='project_list'),
    path('projects/create/', ProjectCreateView.as_view(), name='project_create'),
    path('projects/assign/', project_assignment_view, name='project_assignment'),
    path('projects/<str:code>/edit/', ProjectUpdateView.as_view(), name='project_update'),
    path('projects/<str:code>/add-site/', project_site_create_view, name='project_site_create'),
    path('projects/<str:code>/', ProjectDetailView.as_view(), name='project_detail'),

    path('update_material_receipt/<int:order_id>/<str:new_status>/', update_material_receipt, name='update_material_receipt'),
    path('reports/', ReportSubmissionListView.as_view(), name='report-submission-list'),
    path('reports/new/', ReportSubmissionCreateView.as_view(), name='report-submission-create'),
    path('reports/<int:pk>/', ReportSubmissionDetailView.as_view(), name='report-submission-detail'),
    path('reports/<int:pk>/edit/', ReportSubmissionUpdateView.as_view(), name='report-submission-update'),
    path('reports/<int:pk>/submit/', submit_report, name='report-submission-submit'),
    path('reports/<int:pk>/approve/', approve_report, name='report-submission-approve'),
    path('reports/<int:pk>/reject/', reject_report, name='report-submission-reject'),
    
    # Consultant URLs
    path('consultant/deliveries/', ConsultantDeliveriesView.as_view(), name='consultant_deliveries'),
    path('consultant/site-receipt/<int:transport_id>/', SiteReceiptCreateView.as_view(), name='site_receipt_create'),
    path('consultant/receipts/', SiteReceiptListView.as_view(), name='site_receipts'),
    
    # Transportation and Transport Assignment URLs
    path('transporter-assignment/', transporter_views.TransporterAssignmentView.as_view(), name='transport_assignment'),
    path('transportation-status/', transporter_views.TransportationStatusView.as_view(), name='transportation_status'),
    path('transportation-archive/', transporter_views.TransportArchiveView.as_view(), name='transportation_archive'),
    path('update-transport-status/<int:pk>/', transporter_views.update_transport_status, name='update_transport_status'),
    path('download-waybill/<int:transport_id>/', transporter_views.download_waybill_pdf, name='download_waybill_pdf'),
    path('verify-waybill-qr/<str:waybill_identifier>/', transporter_views.verify_waybill_qr, name='verify_waybill_qr'),

    
    # Transporter management
    path('transporters/', transporter_views.TransporterListView.as_view(), name='transporter_list'),
    path('transporters/add/', transporter_views.TransporterCreateView.as_view(), name='transporter_create'),
    path('transporters/<int:pk>/', transporter_views.TransporterDetailView.as_view(), name='transporter_detail'),
    path('transporters/<int:pk>/edit/', transporter_views.TransporterUpdateView.as_view(), name='transporter_edit'),
    path('transporters/<int:pk>/delete/', transporter_views.TransporterDeleteView.as_view(), name='transporter_delete'),
    
    # Transport vehicle management
    path('vehicles/', transporter_views.TransportVehicleListView.as_view(), name='vehicle_list'),
    path('vehicles/add/', transporter_views.TransportVehicleCreateView.as_view(), name='vehicle_create'),
    path('vehicles/add/<int:transporter_id>/', transporter_views.TransportVehicleCreateView.as_view(), name='vehicle_create'),
    path('vehicles/<int:pk>/', transporter_views.TransportVehicleDetailView.as_view(), name='vehicle_detail'),
    path('vehicles/<int:pk>/edit/', transporter_views.TransportVehicleUpdateView.as_view(), name='vehicle_edit'),
    path('vehicles/<int:pk>/delete/', transporter_views.TransportVehicleDeleteView.as_view(), name='vehicle_delete'),
    
    # Transporter AJAX endpoints
    path('ajax/load-vehicles/', transporter_views.ajax_load_vehicles, name='ajax_load_vehicles'),
    
    # Transporter import/export
    path('transporters/import/', transporter_views.import_transporters, name='transporter_import'),
    path('transporters/export-template/', transporter_views.export_transporters_template, name='transporter_export_template'),
    
    # Transporter legend
    path('transport/legend/', transporter_views.TransporterLegendView.as_view(), name='transporter_legend'),
    
    # Release letter upload and tracking
    path('release-letter/upload/', ReleaseLetterUploadView.as_view(), name='release-letter-upload'),
    path('release-letters/', ReleaseLetterListView.as_view(), name='release_letter_list'),
    path('release-letters/tracking/', release_letter_tracking_dashboard, name='release_letter_tracking_dashboard'),
    path('release-letters/<int:pk>/adjust-quantity/', AdjustReleaseLetterQuantityView.as_view(), name='adjust_release_letter_quantity'),

    # Phase F.1: release-letter detail page + document generation.
    path('release-letters/<int:pk>/', ReleaseLetterDetailView.as_view(), name='release_letter_detail'),
    path('release-letters/<int:pk>/generate-documents/', GenerateReleaseDocumentsView.as_view(), name='generate_release_documents'),
    path('release-letters/<int:pk>/adjust-documents/', AdjustReleaseDocumentsView.as_view(), name='adjust_release_documents'),
    path('release-letters/<int:pk>/preview/memo/', MemoPreviewView.as_view(), name='release_memo_preview'),
    path('release-letters/<int:pk>/preview/letter/', LetterPreviewView.as_view(), name='release_letter_preview'),
    # WYSIWYG: store / discard a hand-edited document body. <kind> is memo|letter.
    path('release-letters/<int:pk>/document/<str:kind>/save/', SaveDocumentHtmlView.as_view(), name='save_document_html'),
    path('release-letters/<int:pk>/document/<str:kind>/revert/', RevertDocumentHtmlView.as_view(), name='revert_document_html'),

    # BoQ reconciliation — computed live, never stored, so it cannot go stale.
    path('release-letters/<int:pk>/reconciliation/', ReconciliationReportView.as_view(),
         name='release_reconciliation'),
    # The way out of an unmatched BoQ line, which the officer cannot fix himself.
    # A block with no door gets routed around rather than resolved.
    path('release-letters/<int:pk>/boq-assistance/', BoQAssistanceView.as_view(),
         name='release_boq_assistance'),
    # The signatory's signing page: both documents, one panel, no officer
    # controls. Distinct from the POST route below, which applies one signature.
    path('release-letters/<int:pk>/sign/', SigningPageView.as_view(), name='sign_release'),
    # The officer's explicit handover. Generation notifies nobody; this does.
    path('release-letters/<int:pk>/send-for-signature/', SendForSignatureView.as_view(),
         name='send_for_signature'),
    # Apply a drawn signature. Permission is the signing chain, not a group.
    path('release-letters/<int:pk>/sign/<str:kind>/', SignDocumentView.as_view(), name='sign_document'),
    # Repair: re-render a signed document whose PDF was minted without its signatures.
    path('release-letters/<int:pk>/rebuild/<str:kind>/', RebuildSignedDocumentView.as_view(), name='rebuild_signed_document'),

    # Email the memo/letter to chosen users or typed addresses (Microsoft Graph).
    path('release-letters/<int:pk>/send/', SendReleaseDocumentsView.as_view(), name='send_release_documents'),

    # Phase 3-5: the signatory's side of the workflow.
    # The queue is a signatory's landing point — the release-letter dashboard is
    # a schedule officer's workspace and shows every release in every state.
    path('approvals/', ApprovalQueueView.as_view(), name='approval_queue'),
    # A conversation, not a rejection: no workflow state changes here.
    path('release-letters/<int:pk>/call-officer/', CallOfficerView.as_view(), name='call_officer'),
    # Management directive clearing MMU to release on the digital signature.
    # Restricted to signatories inside the view, not by group.
    path('release-letters/<int:pk>/urgent/', DeclareUrgentView.as_view(), name='declare_urgent'),
    # So urgency shows up as a trend Internal Audit can watch, rather than as a
    # finding after the fact.
    path('reports/urgent-releases/', UrgentReleasesReportView.as_view(), name='urgent_releases_report'),

    # Historical paper requisitions — records only, no stock or workflow effect.
    path('archive/', ArchiveListView.as_view(), name='archive_list'),
    path('archive/new/', ArchiveCreateView.as_view(), name='archive_create'),
    path('archive/import/', ArchiveBulkImportView.as_view(), name='archive_bulk_import'),
    path('archive/import/template/', ArchiveTemplateView.as_view(), name='archive_template'),
    path('archive/import/errors/', ArchiveImportErrorsView.as_view(), name='archive_import_errors'),
    path('archive/<int:pk>/', ArchiveDetailView.as_view(), name='archive_detail'),

    # Public document verification — reached by scanning the QR on a printed
    # document. No login: the reader may have no account at all. Must also be
    # allowlisted in UserRoleMiddleware, or anonymous scans redirect to signin.
    path('verify/<str:reference>/', VerifyDocumentView.as_view(), name='verify_document'),

    # Letterhead upload + drag-to-calibrate printable area.
    path('settings/letterhead/', LetterheadSettingsView.as_view(), name='letterhead_settings'),

    # Phase F.1: one-click 'Create RL' that replaces the buggy legacy upload page.
    # Takes ?request_code=X, creates the ReleaseLetter, redirects to the detail page.
    path('release-letters/create/', CreateReleaseLetterFromRequestView.as_view(), name='create_release_letter_from_request'),

    # Phase F.2: signed-scan upload, two-person confirmation, mark-released.
    path('release-letters/<int:pk>/upload-scan/', UploadSignedScanView.as_view(), name='release_letter_upload_scan'),
    path('release-letters/<int:pk>/confirm-scan/', ConfirmSignedScanView.as_view(), name='release_letter_confirm_scan'),
    path('release-letters/<int:pk>/mark-released/', MarkReleasedView.as_view(), name='release_letter_mark_released'),

    
    # Notification management
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:pk>/', notification_detail, name='notification_detail'),
    path('notifications/<int:pk>/mark-read/', mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', mark_all_notifications_read, name='mark_all_notifications_read'),
    path('notifications/unread-count/', get_unread_count, name='get_unread_count'),
    path('notifications/<int:pk>/delete/', delete_notification, name='delete_notification'),
    path('notifications/preferences/', notification_preferences, name='notification_preferences'),
    
    # BoQ Overissuance Management
    path('boq/reconciliation/', PackageReconciliationView.as_view(), name='package_reconciliation'),
    path('boq/overissuance/summary/', BoQOverissuanceSummaryView.as_view(), name='boq_overissuance_summary'),
    path('boq/overissuance/<int:boq_id>/justify/', BoQOverissuanceJustificationCreateView.as_view(), name='boq_overissuance_justification_create'),
    path('boq/overissuance/justifications/', BoQOverissuanceJustificationListView.as_view(), name='boq_overissuance_justification_list'),
    path('boq/overissuance/justifications/<int:pk>/', BoQOverissuanceJustificationDetailView.as_view(), name='boq_overissuance_justification_detail'),
    path('boq/overissuance/justifications/<int:pk>/review/', review_overissuance_justification, name='review_overissuance_justification'),
    path('boq/overissuance/stats/', boq_overissuance_stats, name='boq_overissuance_stats'),
    
    # Supply Contract Management
    path('supply/', include('Inventory.supply_contract_urls')),
    
    # Digital Signature Management
    path('signatures/lookup/', signature_lookup, name='signature_lookup'),
    path('signatures/verify/<int:user_id>/', signature_verify, name='signature_verify'),
    path('signatures/api/lookup/', signature_api_lookup, name='signature_api_lookup'),

    
    # Stores Management URLs
    path('stores/pending-orders/', PendingOrdersView.as_view(), name='stores_pending_orders'),
    path('stores/assigned-orders/', AssignedOrdersView.as_view(), name='stores_assigned_orders'),
    path('stores/assign-orders/', AssignOrderView.as_view(), name='stores_assign_orders'),
    path('stores/my-assigned-orders/', MyAssignedOrdersView.as_view(), name='stores_my_assigned_orders'),
    path('stores/assignment/<int:assignment_id>/update-status/', update_assignment_status, name='stores_update_assignment_status'),
    path('stores/bulk-assign/', bulk_assign_orders, name='stores_bulk_assign'),
    path('stores/performance/', StoreOfficerPerformanceDashboard.as_view(), name='stores_performance_dashboard'),
    path('stores/order/<int:order_id>/process-partial/', process_order_partial, name='process_order_partial'),

    # Weekly Report URLs
    path('weekly-reports/', weeklyreport_changelist, name='weekly_reports_list'),
    path('weekly-reports/generate/', generate_weekly_report, name='generate_weekly_report'),
    path('weekly-reports/<int:report_id>/', weeklyreport_changelist, name='weeklyreport_detail'),
    
    # Bulk User Upload
    path('bulk-user-upload/', bulk_user_upload, name='bulk_user_upload'),
    
    # Excel User Import Template Download
    path('download-user-import-template/', 
         lambda request: __import__('Inventory.utils.excel_templates', fromlist=['create_user_import_template_view']).create_user_import_template_view(request),
         name='download_user_import_template'),
    
    # Obsolete Materials Register
    # Tally (bin) cards — stock ledger per material/warehouse
    path('stock-cards/', TallyCardListView.as_view(), name='tally_card_list'),
    path('stock-cards/<int:pk>/', TallyCardDetailView.as_view(), name='tally_card_detail'),
    path('stock-cards/<int:pk>/pdf/', TallyCardPDFView.as_view(), name='tally_card_pdf'),
    path('stock-cards/<int:pk>/export/', TallyCardExcelView.as_view(), name='tally_card_excel'),
    path('stock-cards/<int:pk>/adjust/', tally_card_adjust, name='tally_card_adjust'),
    path('stock-cards-consolidated/', TallyCardConsolidatedView.as_view(), name='tally_card_consolidated'),
    path('stock-ledger-integrity/', StockIntegrityView.as_view(), name='stock_ledger_integrity'),

    path('obsolete-materials/', ObsoleteMaterialListView.as_view(), name='obsolete_material_list'),
    path('obsolete-materials/register/', ObsoleteMaterialRegisterView.as_view(), name='obsolete_material_register'),
    path('obsolete-materials/<int:pk>/', ObsoleteMaterialDetailView.as_view(), name='obsolete_material_detail'),
    path('obsolete-materials/<int:pk>/update-status/', update_obsolete_material_status, name='update_obsolete_material_status'),
    
    # Community management URLs (renamed from shep-communities in Phase B.2).
    # The new canonical paths live under /communities/, with permanent
    # redirects from /shep-communities/* for any external bookmarks.
    # Both URL names (shep_community_* and community_*) resolve so existing
    # template references keep working through the transition.
    path('communities/', SHEPCommunityListView.as_view(), name='community_list'),
    path('communities/add/', SHEPCommunityCreateView.as_view(), name='community_create'),
    path('communities/<int:pk>/edit/', SHEPCommunityUpdateView.as_view(), name='community_update'),
    path('communities/<int:pk>/delete/', SHEPCommunityDeleteView.as_view(), name='community_delete'),

    # Backward-compat URL names — point at the same views so any old
    # template using {% url 'shep_community_list' %} still resolves.
    path('communities/', SHEPCommunityListView.as_view(), name='shep_community_list'),
    path('communities/add/', SHEPCommunityCreateView.as_view(), name='shep_community_create'),
    path('communities/<int:pk>/edit/', SHEPCommunityUpdateView.as_view(), name='shep_community_update'),
    path('communities/<int:pk>/delete/', SHEPCommunityDeleteView.as_view(), name='shep_community_delete'),

    # 301 redirects from the old paths so external bookmarks still land.
    path('shep-communities/', RedirectView.as_view(pattern_name='community_list', permanent=True)),
    path('shep-communities/add/', RedirectView.as_view(pattern_name='community_create', permanent=True)),
    path('shep-communities/<int:pk>/edit/', RedirectView.as_view(pattern_name='community_update', permanent=True)),
    path('shep-communities/<int:pk>/delete/', RedirectView.as_view(pattern_name='community_delete', permanent=True)),

    path('abbreviation-legend/', AbbreviationLegendView.as_view(), name='abbreviation_legend'),
    
    # SHEP Community AJAX endpoints for cascading dropdowns
    path('api/districts-by-region/', get_districts_by_region, name='api_districts_by_region'),
    path('api/communities-by-district/', get_communities_by_district, name='api_communities_by_district'),
    path('api/packages-by-community/', get_packages_by_community, name='api_packages_by_community'),
    path('api/generate-package-number/', generate_auto_package_number, name='api_generate_package_number'),
    # Auto-populate MP from constituency / district / region.
    path('api/mps-by-constituency/', get_mps_by_constituency, name='api_mps_by_constituency'),
    path('api/stock/', stock_for_item, name='api_stock_for_item'),
    
    # Excel Template Downloads
    path('download-material-template/', download_material_template, name='download_material_template'),
    path('download-shep-community-template/', download_shep_community_template, name='download_shep_community_template'),
    path('upload-shep-communities/', upload_shep_communities, name='upload_shep_communities'),

    # Phase B.3: project-aware bulk import.
    # Same view handles all three project templates; pass ?project=shep / cost_sharing / streetlights.
    path('download-community-template/', download_community_template, name='download_community_template'),
    path('upload-communities/', upload_communities, name='upload_communities'),

    # Members of Parliament bulk import.
    path('download-mp-template/', download_mp_template, name='download_mp_template'),
    path('upload-mps/', upload_members_of_parliament, name='upload_mps'),

    # Project consultant bulk import.
    path('download-consultant-template/', download_consultant_template, name='download_consultant_template'),
    path('upload-consultants/', upload_project_consultants, name='upload_consultants'),

    # Geospatial API endpoints (Ghana Map - Phase 2)
    path('api/ghana-map-project-sites/', ghana_map_project_sites_api, name='ghana_map_project_sites_api'),
    path('api/ghana-map-region-heatmap/', ghana_map_region_heatmap_api, name='ghana_map_region_heatmap_api'),
    path('api/ghana-map-stats/', ghana_map_stats_api, name='ghana_map_stats_api'),
    path('api/ghana-map-districts/', ghana_map_districts_api, name='ghana_map_districts_api'),
    path('api/ghana-map-communities/', ghana_map_communities_api, name='ghana_map_communities_api'),
]
