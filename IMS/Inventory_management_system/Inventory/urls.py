from django.urls import path, include, reverse_lazy
from django.conf import settings
from django.conf.urls import handler403, handler404, handler500
from django.contrib.auth import views as auth_views

# Import views from their respective modules
from .views import (
    Index, RequestMaterialView, MaterialOrdersView, UpdateMaterialStatusView, 
    ProfileView, UploadInventoryView, UploadCategoriesAndUnitsView, list_categories, 
    list_units, get_boq_data, MaterialHeatmapView, MaterialLegendView, LowInventorySummaryView, 
    BillOfQuantityView, UploadBillOfQuantityView, consultant_dash, management_dashboard, 
    MaterialReceiptView, update_material_receipt, ReportSubmissionListView, 
    ReportSubmissionCreateView, ReportSubmissionDetailView, ReportSubmissionUpdateView, 
    submit_report, approve_report, reject_report, MaterialTransportView, ReleaseLetterUploadView,
    AdjustReleaseLetterQuantityView,
    StaffProfileView, MaterialOrdersOfficersView, DownloadSampleTemplateView,
    generate_weekly_report, weeklyreport_changelist, bulk_user_upload,
    ObsoleteMaterialRegisterView, ObsoleteMaterialListView, ObsoleteMaterialDetailView,
    update_obsolete_material_status, release_letter_tracking_dashboard,
    AdjustReleaseLetterQuantityView, AboutView, requisition_status,
)
from .views.map_views import ghana_map_view, ghana_map_data_api

# Import project management views
from .project_management_views import (
    ProjectManagementDashboardView,
    CommunityAnalysisView,
    PackageAnalysisView,
    MaterialAnalysisView
)

# Import transporter views
from . import transporter_views
from .transporter_views import (
    TransporterListView, TransporterDetailView, TransporterCreateView, TransporterUpdateView, TransporterDeleteView,
    TransportVehicleListView, TransportVehicleDetailView, TransportVehicleCreateView, TransportVehicleUpdateView, TransportVehicleDeleteView,
    TransporterAssignmentView, TransporterLegendView, import_transporters, export_transporters_template, ajax_load_vehicles,
    TransportationStatusView, update_transport_status, debug_transport_records, create_test_transport, debug_assignment_orders
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
    StoreOfficerPerformanceDashboard, StoreOperationsHubView,
    process_order_partial, store_hub_stats_api
)

# Import SHEP community management views
from .shep_community_views import (
    SHEPCommunityListView, SHEPCommunityCreateView, SHEPCommunityUpdateView,
    SHEPCommunityDeleteView, AbbreviationLegendView,
    get_districts_by_region, get_communities_by_district,
    get_packages_by_community, generate_auto_package_number,
    download_material_template, download_shep_community_template,
    upload_shep_communities
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
    
    # Password Reset URLs
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(
             template_name='Inventory/password_reset_form.html',
             email_template_name='Inventory/emails/password_reset_email.txt',
             html_email_template_name='Inventory/emails/password_reset_email.html',
             subject_template_name='Inventory/emails/password_reset_subject.txt',
             success_url=reverse_lazy('password_reset_done')
         ),
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='Inventory/password_reset_done.html'
         ),
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='Inventory/password_reset_confirm.html',
             success_url=reverse_lazy('password_reset_complete')
         ),
         name='password_reset_confirm'),
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='Inventory/password_reset_complete.html'
         ),
         name='password_reset_complete'),
    
    # Two-Factor Authentication URLs
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
    path('request-material/', RequestMaterialView.as_view(), name='request_material'),
    path('material-orders/', MaterialOrdersView.as_view(), name='material_orders'),
    path('material-orders-officers/', MaterialOrdersOfficersView.as_view(), name='material_orders_officers'),
    path('requisition-status/', requisition_status, name='requisition_status'),
    # Parameterized routes
    path('update_material_status/<int:order_id>/<str:new_status>/', UpdateMaterialStatusView.as_view(), name='update_material_status'),
    path('delete-item/<int:pk>', DeleteItem.as_view(), name='delete-item'),
    path('edit-item/<int:pk>', EditItem.as_view(), name='edit-item'),
    path('upload-inventory/', UploadInventoryView.as_view(), name='upload_inventory'),
    path('download-sample-template/', DownloadSampleTemplateView.as_view(), name='download_sample_template'),
    path('list-categories/', list_categories, name='list_categories'),
    path('list-units/', list_units, name='list_units'),
    path('get-boq-data/', get_boq_data, name='get_boq_data'),
    path('upload-categories-units/', UploadCategoriesAndUnitsView.as_view(), name='upload_categories_units'),
    path('receive-material/', MaterialReceiptView.as_view(), name='material_receipt'),
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
    path('project-management-dashboard/', ProjectManagementDashboardView.as_view(), name='project_management_dashboard'),
    path('ghana-map/', ghana_map_view, name='ghana_map'),
    path('api/ghana-map-data/', ghana_map_data_api, name='ghana_map_data_api'),
    path('project-analysis/community/', CommunityAnalysisView.as_view(), name='project_community_analysis'),
    path('project-analysis/package/', PackageAnalysisView.as_view(), name='project_package_analysis'),
    path('project-analysis/material/', MaterialAnalysisView.as_view(), name='project_material_analysis'),
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
    path('release-letters/tracking/', release_letter_tracking_dashboard, name='release_letter_tracking_dashboard'),
    path('release-letters/<int:pk>/adjust-quantity/', AdjustReleaseLetterQuantityView.as_view(), name='adjust_release_letter_quantity'),

    
    # Notification management
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:pk>/', notification_detail, name='notification_detail'),
    path('notifications/<int:pk>/mark-read/', mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', mark_all_notifications_read, name='mark_all_notifications_read'),
    path('notifications/unread-count/', get_unread_count, name='get_unread_count'),
    path('notifications/<int:pk>/delete/', delete_notification, name='delete_notification'),
    path('notifications/preferences/', notification_preferences, name='notification_preferences'),
    
    # BoQ Overissuance Management
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
    path('stores/hub/', StoreOperationsHubView.as_view(), name='store_operations_hub'),
    path('stores/order/<int:order_id>/process-partial/', process_order_partial, name='process_order_partial'),
    path('stores/hub/api/stats/', store_hub_stats_api, name='store_hub_stats_api'),

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
    path('obsolete-materials/', ObsoleteMaterialListView.as_view(), name='obsolete_material_list'),
    path('obsolete-materials/register/', ObsoleteMaterialRegisterView.as_view(), name='obsolete_material_register'),
    path('obsolete-materials/<int:pk>/', ObsoleteMaterialDetailView.as_view(), name='obsolete_material_detail'),
    path('obsolete-materials/<int:pk>/update-status/', update_obsolete_material_status, name='update_obsolete_material_status'),
    
    # SHEP Community Management URLs
    path('shep-communities/', SHEPCommunityListView.as_view(), name='shep_community_list'),
    path('shep-communities/add/', SHEPCommunityCreateView.as_view(), name='shep_community_create'),
    path('shep-communities/<int:pk>/edit/', SHEPCommunityUpdateView.as_view(), name='shep_community_update'),
    path('shep-communities/<int:pk>/delete/', SHEPCommunityDeleteView.as_view(), name='shep_community_delete'),
    path('abbreviation-legend/', AbbreviationLegendView.as_view(), name='abbreviation_legend'),
    
    # SHEP Community AJAX endpoints for cascading dropdowns
    path('api/districts-by-region/', get_districts_by_region, name='api_districts_by_region'),
    path('api/communities-by-district/', get_communities_by_district, name='api_communities_by_district'),
    path('api/packages-by-community/', get_packages_by_community, name='api_packages_by_community'),
    path('api/generate-package-number/', generate_auto_package_number, name='api_generate_package_number'),
    
    # Excel Template Downloads
    path('download-material-template/', download_material_template, name='download_material_template'),
    path('download-shep-community-template/', download_shep_community_template, name='download_shep_community_template'),
    path('upload-shep-communities/', upload_shep_communities, name='upload_shep_communities'),
]

# Debug-only URLs — only available when DEBUG=True
if settings.DEBUG:
    urlpatterns += [
        path('debug-transport-records/', transporter_views.debug_transport_records, name='debug_transport_records'),
        path('debug-assignment-orders/', transporter_views.debug_assignment_orders, name='debug_assignment_orders'),
        path('create-test-transport/', transporter_views.create_test_transport, name='create_test_transport'),
    ]