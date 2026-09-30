"""Every web address on the site, in one list."""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path, re_path
from django.views.static import serve

from shop import views as v

urlpatterns = [
    # Shop
    path("", v.home, name="home"),
    path("shop/", v.product_list, name="shop"),
    path("category/<slug:slug>/", v.product_list, name="category"),
    path("product/<slug:slug>/", v.product_detail, name="product"),

    # Cart & checkout
    path("cart/", v.cart_view, name="cart"),
    path("cart/add/<int:pk>/", v.cart_add, name="cart_add"),
    path("cart/update/<int:pk>/", v.cart_update, name="cart_update"),
    path("checkout/", v.checkout, name="checkout"),

    # Orders & payments
    path("order/<str:number>/", v.order_detail, name="order_detail"),
    path("order/<str:number>/pay/", v.order_pay, name="order_pay"),
    path("order/<str:number>/simulate/", v.order_simulate_payment, name="order_simulate"),
    path("order/<str:number>/status.json", v.order_status_json, name="order_status"),
    path("track/", v.track_order, name="track_order"),
    path("mpesa/callback/", v.mpesa_callback, name="mpesa_callback"),

    # Customer accounts
    path("signup/", v.signup, name="signup"),
    path("login/", v.CustomerLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("account/", v.account, name="account"),

    # Owner dashboard
    path("dashboard/", v.dash_home, name="dash_home"),
    path("dashboard/products/", v.dash_products, name="dash_products"),
    path("dashboard/products/new/", v.dash_product_form, name="dash_product_new"),
    path("dashboard/products/<int:pk>/edit/", v.dash_product_form, name="dash_product_edit"),
    path("dashboard/products/<int:pk>/stock/", v.dash_product_stock, name="dash_product_stock"),
    path("dashboard/products/<int:pk>/delete/", v.dash_product_delete, name="dash_product_delete"),
    path("dashboard/orders/", v.dash_orders, name="dash_orders"),
    path("dashboard/orders/<str:number>/", v.dash_order, name="dash_order"),
    path("dashboard/categories/", v.dash_categories, name="dash_categories"),
    path("dashboard/categories/<int:pk>/", v.dash_categories, name="dash_category_edit"),
    path("dashboard/settings/", v.dash_settings, name="dash_settings"),

    # Django's built-in admin (backup tool; the dashboard above is what the owner uses)
    path("admin/", admin.site.urls),

    # Uploaded product photos (served by Django so no extra setup is needed on Railway)
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
