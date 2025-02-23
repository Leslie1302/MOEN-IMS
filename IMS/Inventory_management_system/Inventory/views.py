from django.shortcuts import render, redirect
from django.views.generic import TemplateView, View, CreateView, UpdateView, DeleteView, FormView, ListView
from django.contrib.auth import authenticate, login, update_session_auth_hash
from .forms import UserRegistration, AuthenticationForm, InventoryItemForm, InventoryItemFormSet, MaterialOrderForm, UserUpdateForm, ProfileUpdateForm, PasswordChangeForm, ExcelUploadForm
from django.contrib.auth.views import LogoutView
from django.contrib.auth.views import LogoutView as BaseLogoutView
from .models import InventoryItem, Category, Unit, MaterialOrder, Profile
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from Inventory_management_system.settings import LOW_QUANTITY
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
import traceback
from django.utils.decorators import method_decorator
from django.db import transaction 
import pandas as pd
from django.shortcuts import render, redirect
from .forms import ExcelUploadForm, MaterialReceiptFormSet
import json
import seaborn as sns
import matplotlib.pyplot as plt
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import numpy as np

class Index(TemplateView):
    template_name = 'Inventory/index.html'

LOW_QUANTITY = 5  # Set threshold

class Dashboard(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'Inventory.view_inventoryitem'

    def get(self, request):
        user = request.user
        if user.is_superuser:
            # Superusers see all items
            items = InventoryItem.objects.all()
        else:
            # Non-superusers see items associated with their groups
            items = InventoryItem.objects.filter(group__in=user.groups.all())
        low_inventory_items = items.filter(quantity__lte=LOW_QUANTITY)
        low_inventory_ids = list(low_inventory_items.values_list('id', flat=True))
        low_inventory_names = list(low_inventory_items.values_list('name', flat=True))
        return render(request, 'Inventory/dashboard.html', {
            'items': items,
            'low_inventory_ids': low_inventory_ids,
            'low_inventory_items': low_inventory_names
        })

class SignUpView(View):
    def get(self, request):
        form = UserRegistration()
        return render(request, 'Inventory/signup.html', {'form': form})

    def post(self, request):
        form = UserRegistration(request.POST)
        if form.is_valid():
            user = form.save()
            authenticated_user = authenticate(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password1']
            )
            login(request, authenticated_user)
            return redirect('index')
        return render(request, 'Inventory/signup.html', {'form': form})

class SignInView(View):
    def get(self, request):
        form = AuthenticationForm()
        return render(request, 'Inventory/signin.html', {'form': form})

    def post(self, request):
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('index')
        return render(request, 'Inventory/signin.html', {'form': form})

class CustomLogoutView(BaseLogoutView):
    http_method_names = ['get', 'post']

class AddItem(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'Inventory.add_inventoryitem'
    template_name = 'Inventory/item_form.html'

    def get(self, request):
        formset = InventoryItemFormSet()
        return render(request, self.template_name, {'formset': formset})

    def post(self, request):
        formset = InventoryItemFormSet(request.POST)
        if formset.is_valid():
            for form in formset:
                if form.cleaned_data:
                    item = form.save(commit=False)
                    item.user = request.user
                    if request.user.groups.exists():
                        item.group = request.user.groups.first()
                    item.save()
            return redirect(reverse_lazy('dashboard'))
        return render(request, self.template_name, {'formset': formset})

class EditItem(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = 'Inventory/item_form.html'
    success_url = reverse_lazy('dashboard')
    permission_required = 'Inventory.change_inventoryitem'

    def get_queryset(self):
        # Ensure users can only edit items in their groups
        if self.request.user.is_superuser:
            return InventoryItem.objects.all()
        return InventoryItem.objects.filter(group__in=self.request.user.groups.all())

class DeleteItem(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = InventoryItem
    template_name = 'Inventory/delete_item.html'
    success_url = reverse_lazy('dashboard')
    context_object_name = 'item'
    permission_required = 'Inventory.delete_inventoryitem'

    def get_queryset(self):
        # Ensure users can only delete items in their groups
        if self.request.user.is_superuser:
            return InventoryItem.objects.all()
        return InventoryItem.objects.filter(group__in=self.request.user.groups.all())

MaterialOrderFormSet = formset_factory(MaterialOrderForm, extra=1)

MaterialOrderFormSet = formset_factory(MaterialOrderForm, extra=1)

class RequestMaterialView(LoginRequiredMixin, View):
    template_name = 'Inventory/request_material.html'

    def get(self, request):
        if request.user.is_superuser:
            items = InventoryItem.objects.all()
        else:
            items = InventoryItem.objects.filter(group__in=request.user.groups.all())

        formset = MaterialOrderFormSet(form_kwargs={'user': request.user})
        inventory_items = list(items.values('name', 'category__name', 'unit__name', 'code'))

        return render(request, self.template_name, {
            'formset': formset,
            'items': items,
            'inventory_items': json.dumps(inventory_items)
        })

    def post(self, request):
        formset = MaterialOrderFormSet(request.POST, form_kwargs={'user': request.user})
        if formset.is_valid():
            for form in formset:
                if form.cleaned_data:
                    material_order = form.save(commit=False)
                    selected_item = InventoryItem.objects.filter(name=form.cleaned_data['name']).first()
                    if selected_item:
                        material_order.category = selected_item.category
                        material_order.code = selected_item.code
                        material_order.unit = selected_item.unit
                    material_order.user = request.user
                    material_order.group = request.user.groups.first() if request.user.groups.exists() else None
                    material_order.request_type = 'Release'  # Set as Release Request
                    material_order.save()
            messages.success(request, "Material requests submitted successfully!")
            return redirect('material_orders')
        else:
            print("Formset errors:", formset.errors)
            messages.error(request, "There was an error with your submission.")
        
        if request.user.is_superuser:
            items = InventoryItem.objects.all()
        else:
            items = InventoryItem.objects.filter(group__in=request.user.groups.all())
        return render(request, self.template_name, {
            'formset': formset,
            'items': items,
            'inventory_items': json.dumps(list(items.values('name', 'category__name', 'unit__name', 'code')))
        })

class MaterialOrdersView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    template_name = 'Inventory/material_orders.html'
    context_object_name = 'orders'
    permission_required = 'Inventory.view_materialorder'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return MaterialOrder.objects.all().order_by('-date_requested')
        return MaterialOrder.objects.filter(group__in=self.request.user.groups.all()).order_by('-date_requested')


class UpdateMaterialStatusView(View):
    def post(self, request, order_id, new_status):
        if new_status not in ["Seen", "Partial", "Full"]:
            return JsonResponse({"success": False, "error": "Invalid status."}, status=400)

        try:
            with transaction.atomic():
                order = get_object_or_404(MaterialOrder, id=order_id)
                data = json.loads(request.body) if request.body else {}
                is_partial = new_status == "Partial" or data.get('is_partial', False)
                partial_quantity = int(data.get('partial_quantity', 0)) if is_partial else 0
                quantity_to_process = partial_quantity if is_partial else order.remaining_quantity

                # Ensure remaining_quantity is an integer
                if order.remaining_quantity is None:
                    print(f"Warning: remaining_quantity was None for order {order.id}, setting to {order.quantity - order.processed_quantity}")
                    order.remaining_quantity = order.quantity - order.processed_quantity
                    order.save()

                inventory_item = InventoryItem.objects.filter(name=order.name).first()
                if not inventory_item:
                    return JsonResponse({"success": False, "error": "No matching inventory item found for this order."}, status=400)

                # Debugging: Log all relevant details
                print(f"Order ID: {order_id}, Item: {inventory_item.name}, Inventory Quantity: {inventory_item.quantity}, "
                      f"Request Type: {order.request_type}, To Process: {quantity_to_process}, "
                      f"Processed: {order.processed_quantity}, Remaining: {order.remaining_quantity}")

                if new_status == "Seen":
                    order.status = "Seen"
                    order.save()
                elif new_status in ["Partial", "Full"]:
                    if is_partial and (partial_quantity <= 0 or partial_quantity > order.remaining_quantity):
                        return JsonResponse({"success": False, "error": "Invalid partial quantity."}, status=400)

                    if inventory_item.quantity is None:
                        if order.request_type == "Receipt":
                            inventory_item.quantity = 0  # Initialize for receipts
                        else:  # Release
                            return JsonResponse({
                                "success": False,
                                "error": "Inventory quantity is not set for this item."
                            }, status=400)

                    if order.request_type == "Release":
                        if inventory_item.quantity < quantity_to_process:
                            return JsonResponse({
                                "success": False,
                                "error": "The inventory for this material is less than the order quantity"
                            }, status=400)
                        inventory_item.quantity -= quantity_to_process
                    elif order.request_type == "Receipt":
                        inventory_item.quantity += quantity_to_process

                    inventory_item.save()
                    order.processed_quantity += quantity_to_process
                    order.remaining_quantity -= quantity_to_process

                    if order.remaining_quantity <= 0:
                        order.status = "Completed"  # Fully processed
                    else:
                        order.status = "Approved"  # Partially processed or reset after action
                    order.save()

                return JsonResponse({
                    "success": True,
                    "new_status": order.status,
                    "processed_quantity": order.processed_quantity,
                    "remaining_quantity": order.remaining_quantity
                })
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid request data."}, status=400)
        except ValueError as e:  # Handles invalid partial_quantity conversion
            return JsonResponse({"success": False, "error": f"Invalid quantity value: {str(e)}"}, status=400)
        except Exception as e:
            print(f"Unexpected error: {str(e)}")  # Log the full error for debugging
            return JsonResponse({"success": False, "error": f"Server error: {str(e)}"}, status=500)


class ProfileView(LoginRequiredMixin, View):
    template_name = 'Inventory/profile.html'
    permission_required = 'Inventory.view_profile'

    def get(self, request, *args, **kwargs):
        profile, created = Profile.objects.get_or_create(user=request.user)
        if not profile.profile_picture:
            profile.profile_picture = None
        context = {
            'user_form': UserUpdateForm(instance=request.user),
            'profile_form': ProfileUpdateForm(instance=profile),
            'password_form': PasswordChangeForm(),
            'profile': profile
        }
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        profile, created = Profile.objects.get_or_create(user=request.user)
        if not profile.profile_picture:
            profile.profile_picture = None
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        password_form = PasswordChangeForm(request.POST)
        
        if 'update_info' in request.POST:
            if user_form.is_valid() and profile_form.is_valid():
                user_form.save()
                profile_form.save()
                messages.success(request, 'Your profile has been updated!')
                return redirect('profile')
        elif 'change_password' in request.POST:
            if password_form.is_valid():
                user = request.user
                if user.check_password(password_form.cleaned_data['old_password']):
                    user.set_password(password_form.cleaned_data['new_password'])
                    user.save()
                    update_session_auth_hash(request, user)
                    messages.success(request, 'Your password has been updated!')
                    return redirect('profile')
                else:
                    messages.error(request, 'Old password is incorrect.')
        
        context = {
            'user_form': user_form,
            'profile_form': profile_form,
            'password_form': password_form,
            'profile': profile
        }
        return render(request, self.template_name, context)


class UploadInventoryView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser  # ✅ Only allow admins

    def get(self, request):
        form = ExcelUploadForm()
        return render(request, 'Inventory/upload_inventory.html', {'form': form})

    def post(self, request):
        if not self.request.user.is_superuser:
            return JsonResponse({'error': 'Unauthorized access'}, status=403)

        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            try:
                # Read Excel File
                df = pd.read_excel(file, engine='openpyxl')

                # Required columns in Excel
                required_columns = ['name', 'quantity', 'category', 'code', 'unit']
                if not all(col in df.columns for col in required_columns):
                    messages.error(request, "Excel file is missing required columns.")
                    return redirect('dashboard')

                # 🔹 Load category & unit mappings from DB
                category_mapping = {c.name: c.id for c in Category.objects.all()}
                unit_mapping = {u.name: u.id for u in Unit.objects.all()}

                for index, row in df.iterrows():
                    # 🔄 Convert category & unit names to IDs
                    category_id = category_mapping.get(row['category'])
                    unit_id = unit_mapping.get(row['unit'])

                    if not category_id or not unit_id:
                        messages.error(request, f"Error: Invalid category or unit at row {index + 2}")
                        continue

                    item, created = InventoryItem.objects.get_or_create(
                        code=row['code'],
                        defaults={
                            'name': row['name'],
                            'quantity': row['quantity'],
                            'category_id': category_id,
                            'unit_id': unit_id,
                            'user': request.user
                        }
                    )
                    if not created:
                        item.quantity += row['quantity']
                        item.save()

                messages.success(request, "Inventory updated successfully!")
            except Exception as e:
                messages.error(request, f"Error processing file: {e}")

            return redirect('dashboard')

        return render(request, 'Inventory/upload_inventory.html', {'form': form})

class UploadCategoriesAndUnitsView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser  # ✅ Only allow admins

    def get(self, request):
        form = ExcelUploadForm()
        return render(request, 'Inventory/upload_categories_units.html', {'form': form})

    def post(self, request):
        if not self.request.user.is_superuser:
            return JsonResponse({'error': 'Unauthorized access'}, status=403)

        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            try:
                # Read Excel File
                df = pd.read_excel(file, engine='openpyxl')

                # 🔥 Column Mapping: Convert Excel Columns to Match Model Fields
                column_mapping = {
                    'CATEGORY': 'category',
                    'UNIT': 'unit'
                }
                df.rename(columns=column_mapping, inplace=True)

                # ✅ Add Categories to Database
                unique_categories = df['category'].dropna().unique()
                for category_name in unique_categories:
                    Category.objects.get_or_create(name=category_name)

                # ✅ Add Units to Database
                unique_units = df['unit'].dropna().unique()
                for unit_name in unique_units:
                    Unit.objects.get_or_create(name=unit_name)

                messages.success(request, "Categories and Units uploaded successfully!")
            except Exception as e:
                messages.error(request, f"Error processing file: {e}")

            return redirect('dashboard')

        return render(request, 'Inventory/upload_categories_units.html', {'form': form})



def list_categories(request):
    categories = list(Category.objects.values('id', 'name'))
    return JsonResponse({'categories': categories})


def list_units(request):
    units = list(Unit.objects.values('id', 'name'))
    return JsonResponse({'units': units})


class MaterialReceiptView(LoginRequiredMixin, View):
    template_name = 'Inventory/material_receipt.html'

    def get(self, request):
        if request.user.is_superuser:
            items = InventoryItem.objects.all()
        else:
            items = InventoryItem.objects.filter(group__in=request.user.groups.all())

        formset = MaterialOrderFormSet(form_kwargs={'user': request.user})
        inventory_items = list(items.values('name', 'category__name', 'unit__name', 'code'))

        return render(request, self.template_name, {
            'formset': formset,
            'items': items,
            'inventory_items': json.dumps(inventory_items)
        })

    def post(self, request):
        formset = MaterialOrderFormSet(request.POST, form_kwargs={'user': request.user})
        if formset.is_valid():
            for form in formset:
                if form.cleaned_data:
                    material_order = form.save(commit=False)
                    selected_item = InventoryItem.objects.filter(name=form.cleaned_data['name']).first()
                    if selected_item:
                        material_order.category = selected_item.category
                        material_order.code = selected_item.code
                        material_order.unit = selected_item.unit
                    material_order.user = request.user
                    material_order.group = request.user.groups.first() if request.user.groups.exists() else None
                    material_order.request_type = 'Receipt'  # Set as Receipt Request
                    material_order.save()
            messages.success(request, "Material receipts submitted successfully!")
            return redirect('material_orders')
        else:
            print("Formset errors:", formset.errors)
            messages.error(request, "There was an error with your submission.")

        if request.user.is_superuser:
            items = InventoryItem.objects.all()
        else:
            items = InventoryItem.objects.filter(group__in=request.user.groups.all())
        return render(request, self.template_name, {
            'formset': formset,
            'items': items,
            'inventory_items': json.dumps(list(items.values('name', 'category__name', 'unit__name', 'code')))
        })


class MaterialHeatmapView(LoginRequiredMixin, View):
    template_name = 'Inventory/material_heatmap.html'

    def get(self, request):
        if request.user.is_superuser:
            orders = MaterialOrder.objects.all()
            items = InventoryItem.objects.all()
        else:
            orders = MaterialOrder.objects.filter(group__in=request.user.groups.all())
            items = InventoryItem.objects.filter(group__in=request.user.groups.all())

        period = request.GET.get('period', 'month')
        report_type = request.GET.get('type', 'release')

        if report_type in ['release', 'receipt']:
            orders = orders.filter(request_type=report_type.capitalize())
            df = pd.DataFrame.from_records(orders.values('code', 'processed_quantity', 'date_requested'))  # Use 'code' instead of 'name'
            if df.empty:
                df = pd.DataFrame(columns=['code', 'processed_quantity', 'date_requested'])
            else:
                df['date'] = pd.to_datetime(df['date_requested'])
                if period == 'day':
                    df['period'] = df['date'].dt.date
                elif period == 'week':
                    df['period'] = df['date'].dt.to_period('W').apply(lambda r: r.start_time.date())
                else:  # month
                    df['period'] = df['date'].dt.to_period('M').apply(lambda r: r.start_time.date())
                pivot = pd.pivot_table(df, values='processed_quantity', index='code', columns='period', aggfunc='sum', fill_value=0)  # Use 'code' for index
        else:
            df = pd.DataFrame.from_records(items.values('code', 'quantity'))  # Use 'code' instead of 'name'
            pivot = df.set_index('code').T  # Use 'code' for index

        # Set up a professional, modern style heatmap
        plt.figure(figsize=(15, 10))  # Larger figure for better visibility
        sns.set_style("whitegrid")  # Clean, modern background
        heatmap = sns.heatmap(
            pivot,
            cmap="Blues",  # Vibrant blue palette matching your reference (similar to teal/navy)
            annot=True,  # Show values
            fmt='.0f',  # Integer format
            cbar_kws={'label': 'Quantity', 'shrink': 0.8, 'pad': 0.02, 'orientation': 'vertical'},
            linewidths=0.5,  # Thin lines for grid
            annot_kws={'size': 10, 'weight': 'bold'},  # Bold, readable annotations
            square=True,  # Square cells for clarity
            vmin=0,  # Minimum value for color scale
            vmax=pivot.max().max() * 1.1  # Scale max slightly higher for contrast
        )
        plt.title("Material Movement Heatmap", fontsize=16, pad=20, fontweight='bold', color='#2c3e50')  # Navy title
        plt.xlabel("Time Period", fontsize=12, color='#2c3e50')
        plt.ylabel("Material Code", fontsize=12, color='#2c3e50')  # Updated to "Material Code"
        
        # Rotate x-axis labels for readability
        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.yticks(fontsize=10)

        # Adjust layout for a clean look
        plt.tight_layout()

        # Save to buffer
        buffer = BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=300)  # Higher DPI for quality
        plt.close()
        buffer.seek(0)
        heatmap_image = buffer.getvalue()

        context = {
            'heatmap_image': heatmap_image.hex(),
            'report_type': report_type,
            'period': period,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        if request.user.is_superuser:
            orders = MaterialOrder.objects.all()
            items = InventoryItem.objects.all()
        else:
            orders = MaterialOrder.objects.filter(group__in=request.user.groups.all())
            items = InventoryItem.objects.filter(group__in=request.user.groups.all())

        period = request.POST.get('period', 'month')
        report_type = request.POST.get('type', 'release')

        if report_type in ['release', 'receipt']:
            orders = orders.filter(request_type=report_type.capitalize())
            df = pd.DataFrame.from_records(orders.values('code', 'processed_quantity', 'date_requested'))
            if df.empty:
                df = pd.DataFrame(columns=['code', 'processed_quantity', 'date_requested'])
            else:
                df['date'] = pd.to_datetime(df['date_requested'])
                if period == 'day':
                    df['period'] = df['date'].dt.date
                elif period == 'week':
                    df['period'] = df['date'].dt.to_period('W').apply(lambda r: r.start_time.date())
                else:  # month
                    df['period'] = df['date'].dt.to_period('M').apply(lambda r: r.start_time.date())
                pivot = pd.pivot_table(df, values='processed_quantity', index='code', columns='period', aggfunc='sum', fill_value=0)
        else:
            df = pd.DataFrame.from_records(items.values('code', 'quantity'))
            pivot = df.set_index('code').T

        # Set up a professional, modern style heatmap for PDF
        plt.figure(figsize=(15, 10))
        sns.set_style("whitegrid")
        heatmap = sns.heatmap(
            pivot,
            cmap="Blues",
            annot=True,
            fmt='.0f',
            cbar_kws={'label': 'Quantity', 'shrink': 0.8, 'pad': 0.02, 'orientation': 'vertical'},
            linewidths=0.5,
            annot_kws={'size': 10, 'weight': 'bold'},
            square=True,
            vmin=0,
            vmax=pivot.max().max() * 1.1
        )
        plt.title(f"{report_type.capitalize()} Heatmap ({period.capitalize()})", fontsize=16, pad=20, fontweight='bold', color='#2c3e50')
        plt.xlabel("Time Period", fontsize=12, color='#2c3e50')
        plt.ylabel("Material Code", fontsize=12, color='#2c3e50')

        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.yticks(fontsize=10)
        plt.tight_layout()

        # Save to PDF buffer
        buffer = BytesIO()
        plt.savefig(buffer, format='pdf', bbox_inches='tight', dpi=300)
        plt.close()
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{report_type}_heatmap_{period}.pdf"'
        return response