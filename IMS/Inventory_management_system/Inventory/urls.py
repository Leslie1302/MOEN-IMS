from django.urls import path
from django.conf import settings
from django.conf.urls import handler403, handler404, handler500

# Import views from their respective modules
from .views import (
    Index, RequestMaterialView, MaterialOrdersView, UpdateMaterialStatusView, 
    ProfileView, UploadInventoryView, UploadCategoriesAndUnitsView, list_categories, 
    list_units, MaterialHeatmapView, MaterialLegendView, LowInventorySummaryView, 
    BillOfQuantityView, UploadBillOfQuantityView, consultant_dash, management_dashboard, 
    MaterialReceiptView, update_material_receipt, ReportSubmissionListView, 
    ReportSubmissionCreateView, ReportSubmissionUpdateView, ReportSubmissionDetailView, 
    submit_report, approve_report, reject_report, MaterialTransportView, ReleaseLetterUploadView
)

# Import transporter views
from .transporter_views import (
    TransporterListView, TransporterDetailView, TransporterCreateView, TransporterUpdateView, TransporterDeleteView,
    TransportVehicleListView, TransportVehicleDetailView, TransportVehicleCreateView, TransportVehicleUpdateView, TransportVehicleDeleteView,
    TransporterAssignmentView, TransporterLegendView, import_transporters, export_transporters_template, ajax_load_vehicles
)

# Import help view
from .views_help import HelpView

# Import auth views
from .auth_views import SignUpView, SignInView, CustomLogoutView, Dashboard
from .views_auth import AwaitingAuthorizationView, custom_403_view, custom_404_view, custom_500_view

# Error handlers
handler403 = custom_403_view
handler404 = custom_404_view
handler500 = custom_500_view

# Import auth views
from .auth_views import SignUpView, SignInView, CustomLogoutView, Dashboard

# Import item views
from .item_views import AddItem, EditItem, DeleteItem

urlpatterns = [
    # Public routes
    path('', Index.as_view(), name='index'),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('signin/', SignInView.as_view(), name='signin'),
    path('logout/', CustomLogoutView.as_view(template_name='Inventory/logout.html'), name='logout'),
    path('awaiting-authorization/', AwaitingAuthorizationView.as_view(), name='awaiting_authorization'),
    path('help/', HelpView.as_view(), name='help'),
    
    # Authenticated routes
    path('dashboard/', Dashboard.as_view(), name='dashboard'),
    path('add-item', AddItem.as_view(), name='add-item'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('request-material/', RequestMaterialView.as_view(), name='request_material'),
    path('material-orders/', MaterialOrdersView.as_view(), name='material_orders'),
    
    # Parameterized routes
    path('update_material_status/<int:order_id>/<str:new_status>/', UpdateMaterialStatusView.as_view(), name='update_material_status'),
    path('delete-item/<int:pk>', DeleteItem.as_view(), name='delete-item'),
    path('edit-item/<int:pk>', EditItem.as_view(), name='edit-item'),
    path('upload-inventory/', UploadInventoryView.as_view(), name='upload_inventory'),
    path('list-categories/', list_categories, name='list_categories'),
    path('list-units/', list_units, name='list_units'),
    path('upload-categories-units/', UploadCategoriesAndUnitsView.as_view(), name='upload_categories_units'),
    path('receive-material/', MaterialReceiptView.as_view(), name='material_receipt'),
    path('material-heatmap/', MaterialHeatmapView.as_view(), name='material_heatmap'),
    path('material-legend/', MaterialLegendView.as_view(), name='material_legend'),
    path('low-inventory-summary/', LowInventorySummaryView.as_view(), name='low_inventory_summary'),
    path('bill-of-quantity/', BillOfQuantityView.as_view(), name='bill_of_quantity'),
    path('upload-bill-of-quantity/', UploadBillOfQuantityView.as_view(), name='upload_bill_of_quantity'),
    path('consultant_dash/', consultant_dash, name='consultant_dash'),
    path('management_dashboard/', management_dashboard, name='management_dashboard'),
    path('update_material_receipt/<int:order_id>/<str:new_status>/', update_material_receipt, name='update_material_receipt'),
    path('reports/', ReportSubmissionListView.as_view(), name='report-submission-list'),
    path('reports/new/', ReportSubmissionCreateView.as_view(), name='report-submission-create'),
    path('reports/<int:pk>/', ReportSubmissionDetailView.as_view(), name='report-submission-detail'),
    path('reports/<int:pk>/edit/', ReportSubmissionUpdateView.as_view(), name='report-submission-update'),
    path('reports/<int:pk>/submit/', submit_report, name='report-submission-submit'),
    path('reports/<int:pk>/approve/', approve_report, name='report-submission-approve'),
    path('reports/<int:pk>/reject/', reject_report, name='report-submission-reject'),
    
    # Transport-related routes
    path('transport/dashboard/', MaterialTransportView.as_view(), name='transport_dash'),  # Dashboard
    path('transport/list/', MaterialTransportView.as_view(), name='transport_list'),  # List
    path('transport/create/', MaterialTransportView.as_view(), name='transport_form'),  # Create form
    path('transport/<int:pk>/', MaterialTransportView.as_view(), name='transport_detail'),  # Detail
    
    # Transporter management
    path('transporters/', TransporterListView.as_view(), name='transporter_list'),
    path('transporters/add/', TransporterCreateView.as_view(), name='transporter_create'),
    path('transporters/<int:pk>/', TransporterDetailView.as_view(), name='transporter_detail'),
    path('transporters/<int:pk>/edit/', TransporterUpdateView.as_view(), name='transporter_edit'),
    path('transporters/<int:pk>/delete/', TransporterDeleteView.as_view(), name='transporter_delete'),
    
    # Transport vehicle management
    path('vehicles/', TransportVehicleListView.as_view(), name='vehicle_list'),
    path('vehicles/add/', TransportVehicleCreateView.as_view(), name='vehicle_create'),
    path('vehicles/<int:pk>/', TransportVehicleDetailView.as_view(), name='vehicle_detail'),
    path('vehicles/<int:pk>/edit/', TransportVehicleUpdateView.as_view(), name='vehicle_edit'),
    path('vehicles/<int:pk>/delete/', TransportVehicleDeleteView.as_view(), name='vehicle_delete'),
    
    # Transport assignment
    path('transport/assign/', TransporterAssignmentView.as_view(), name='transport_assignment'),
    
    # Transporter AJAX endpoints
    path('ajax/load-vehicles/', ajax_load_vehicles, name='ajax_load_vehicles'),
    
    # Transporter import/export
    path('transporters/import/', import_transporters, name='transporter_import'),
    path('transporters/export-template/', export_transporters_template, name='transporter_export_template'),
    
    # Transporter legend
    path('transport/legend/', TransporterLegendView.as_view(), name='transporter_legend'),
    
    # Release letter upload
    path('release-letter/upload/', ReleaseLetterUploadView.as_view(), name='release-letter-upload'),
]