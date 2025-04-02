from django.urls import path
from .views import (
    Index, SignUpView, SignInView, CustomLogoutView, Dashboard, AddItem, 
    EditItem, DeleteItem, RequestMaterialView, MaterialOrdersView, 
    UpdateMaterialStatusView, ProfileView, UploadInventoryView, UploadCategoriesAndUnitsView, list_categories, list_units, 
    MaterialHeatmapView, LowInventorySummaryView, BillOfQuantityView, UploadBillOfQuantityView, consultant_dash, management_dashboard, 
    MaterialReceiptView, update_material_receipt, ReportSubmissionListView, ReportSubmissionCreateView, ReportSubmissionUpdateView, 
    ReportSubmissionDetailView, submit_report, approve_report, reject_report, MaterialTransportView,
)

urlpatterns = [
    # Public routes
    path('', Index.as_view(), name='index'),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('signin/', SignInView.as_view(), name='signin'),
    path('logout/', CustomLogoutView.as_view(template_name='Inventory/logout.html'), name='logout'),
    
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
    path('transport_dash/', MaterialTransportView.as_view(), name='transport_dash'),  # Dashboard
    path('transport_list/', MaterialTransportView.as_view(), name='transport_list'),  # List
    path('transport_form/', MaterialTransportView.as_view(), name='transport_form'),  # Create form
    path('transport_detail/<int:pk>/', MaterialTransportView.as_view(), name='transport_detail'),  # Detail
]