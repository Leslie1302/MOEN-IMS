"""
URL Configuration for Supply Contract Management
"""
from django.urls import path
from . import supply_contract_views as sc_views

urlpatterns = [
    # Supplier URLs
    path('suppliers/', sc_views.SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/add/', sc_views.SupplierCreateView.as_view(), name='supplier_create'),
    path('suppliers/<int:pk>/', sc_views.SupplierDetailView.as_view(), name='supplier_detail'),
    path('suppliers/<int:pk>/edit/', sc_views.SupplierUpdateView.as_view(), name='supplier_update'),
    
    # Price Catalog URLs
    path('prices/', sc_views.PriceCatalogListView.as_view(), name='price_catalog_list'),
    path('prices/add/', sc_views.PriceCatalogCreateView.as_view(), name='price_catalog_create'),
    
    # Contract URLs
    path('contracts/', sc_views.ContractListView.as_view(), name='contract_list'),
    path('contracts/add/', sc_views.ContractCreateView.as_view(), name='contract_create'),
    path('contracts/<int:pk>/', sc_views.ContractDetailView.as_view(), name='contract_detail'),
    
    # Invoice URLs
    path('invoices/', sc_views.InvoiceListView.as_view(), name='invoice_list'),
    path('invoices/add/', sc_views.InvoiceCreateView.as_view(), name='invoice_create'),
    path('invoices/<int:pk>/', sc_views.InvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/<int:pk>/verify/', sc_views.verify_invoice, name='invoice_verify'),
    path('invoices/<int:pk>/approve/', sc_views.approve_invoice, name='invoice_approve'),
    path('invoices/<int:pk>/mark-paid/', sc_views.mark_invoice_paid, name='invoice_mark_paid'),
]
