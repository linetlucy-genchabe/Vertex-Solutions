from django.contrib import admin

from .models import Category, Order, OrderItem, Product, ShopSettings


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["number", "full_name", "phone", "total", "payment_method", "status", "created"]
    list_filter = ["status", "payment_method"]
    search_fields = ["number", "full_name", "phone"]
    inlines = [OrderItemInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "price", "stock", "is_active", "is_featured"]
    list_filter = ["category", "is_active", "is_featured"]
    search_fields = ["name", "brand"]


admin.site.register(Category)
admin.site.register(ShopSettings)
