"""
Every page of the site, in one file, grouped into sections:
  1. Shared helpers (cart, shop info available to every template)
  2. Shop pages customers see
  3. Cart & checkout
  4. Order pages, M-Pesa and WhatsApp
  5. Customer accounts
  6. Owner dashboard
"""
import json
from datetime import timedelta
from functools import wraps
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import mpesa
from .forms import (CategoryForm, CheckoutForm, EmailLoginForm, OrderStatusForm, ProductForm, ShopSettingsForm,
                    SignupForm, TrackOrderForm)
from .models import Category, Order, OutOfStock, Product, ShopSettings, place_order

PAID_STATUSES = [Order.PAID, Order.DISPATCHED, Order.COMPLETED]


# =====================================================================
# 1. Shared helpers
# =====================================================================

class Cart:
    """Cart kept in the visitor's session: {"product_id": quantity}."""

    def __init__(self, request):
        self.session = request.session
        self.data = self.session.setdefault("cart", {})

    def save(self):
        self.session.modified = True

    def set(self, product, qty):
        qty = max(0, min(int(qty), product.stock))
        if qty:
            self.data[str(product.pk)] = qty
        else:
            self.data.pop(str(product.pk), None)
        self.save()
        return qty

    def add(self, product, qty=1):
        return self.set(product, self.data.get(str(product.pk), 0) + int(qty))

    def remove(self, product_id):
        self.data.pop(str(product_id), None)
        self.save()

    def clear(self):
        self.session["cart"] = {}
        self.save()

    def lines(self):
        products = Product.objects.filter(pk__in=self.data.keys(), is_active=True)
        lines = []
        for p in products:
            qty = self.data[str(p.pk)]
            lines.append({"product": p, "qty": qty, "total": p.price * qty, "too_many": qty > p.stock})
        return lines

    def count(self):
        return sum(self.data.values())


def low_stock_qs():
    default = ShopSettings.get().low_stock_default
    return (Product.objects.filter(is_active=True)
            .annotate(level=Coalesce(F("low_stock_alert"), Value(default)))
            .filter(stock__lte=F("level")).order_by("stock", "name"))


def shop_context(request):
    """Makes shop details, cart count and categories available on every page."""
    shop = ShopSettings.get()
    ctx = {
        "shop": shop,
        "cart_count": Cart(request).count(),
        "nav_categories": Category.objects.all(),
        "wa_link": f"https://wa.me/{shop.whatsapp_number}?text=" + quote(f"Hello {shop.shop_name}, I have an enquiry."),
    }
    if request.user.is_authenticated and request.user.is_staff:
        ctx["low_stock_count"] = low_stock_qs().count()
        ctx["new_orders_count"] = Order.objects.filter(status__in=[Order.PENDING, Order.PAID]).count()
    return ctx


def remember_order(request, order):
    mine = request.session.get("my_orders", [])
    if order.number not in mine:
        mine.append(order.number)
        request.session["my_orders"] = mine[-20:]


def can_view_order(request, order):
    u = request.user
    return (u.is_authenticated and (u.is_staff or order.user_id == u.id)) or \
        order.number in request.session.get("my_orders", [])


def whatsapp_order_link(order):
    shop = ShopSettings.get()
    lines = [f"Hello {shop.shop_name}, I'd like to order:"]
    for it in order.items.all():
        lines.append(f"• {it.quantity} × {it.name} — KES {it.line_total:,}")
    if order.delivery_fee:
        lines.append(f"Delivery: KES {order.delivery_fee:,}")
    lines += [
        f"Total: KES {order.total:,}",
        f"Order no: {order.number}",
        f"Name: {order.full_name} ({order.phone})",
        "Pick up at the shop" if order.delivery_method == Order.PICKUP else f"Deliver to: {order.address}",
    ]
    return f"https://wa.me/{shop.whatsapp_number}?text=" + quote("\n".join(lines))


# =====================================================================
# 2. Shop pages
# =====================================================================

def active_products():
    return Product.objects.filter(is_active=True).select_related("category")


def home(request):
    products = active_products()
    return render(request, "shop/home.html", {
        "offers": products.filter(old_price__gt=F("price"), stock__gt=0)[:8],
        "featured": products.filter(is_featured=True)[:8],
        "latest": products[:12],
        "categories": Category.objects.annotate(n=Count("products", filter=Q(products__is_active=True))),
    })


def product_list(request, slug=None):
    products = active_products()
    category = None
    title = "All products"
    if slug:
        category = get_object_or_404(Category, slug=slug)
        products = products.filter(category=category)
        title = category.name
    q = request.GET.get("q", "").strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(short_specs__icontains=q)
                                   | Q(category__name__icontains=q) | Q(description__icontains=q))
        title = f'Results for "{q}"'
    if request.GET.get("offers"):
        products = products.filter(old_price__gt=F("price"))
        title = "Offers"
    if request.GET.get("instock"):
        products = products.filter(stock__gt=0)
    sort = request.GET.get("sort", "new")
    products = products.order_by({"low": "price", "high": "-price"}.get(sort, "-created"))
    return render(request, "shop/list.html", {"products": products, "category": category, "title": title,
                                              "q": q, "sort": sort})


def product_detail(request, slug):
    product = get_object_or_404(active_products(), slug=slug)
    shop = ShopSettings.get()
    ask = quote(f"Hello {shop.shop_name}, is this available? {product.name} — KES {product.price:,} "
                f"{request.build_absolute_uri(product.get_absolute_url())}")
    related = active_products().filter(category=product.category).exclude(pk=product.pk)[:4]
    return render(request, "shop/product.html", {"product": product, "related": related,
                                                 "ask_link": f"https://wa.me/{shop.whatsapp_number}?text={ask}"})


# =====================================================================
# 3. Cart & checkout
# =====================================================================

@require_POST
def cart_add(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    if not product.in_stock:
        messages.error(request, f"Sorry, {product.name} is out of stock.")
    else:
        before = Cart(request).data.get(str(pk), 0)
        after = Cart(request).add(product, request.POST.get("qty", 1))
        if after == before:
            messages.warning(request, f"Only {product.stock} of {product.name} available.")
        else:
            messages.success(request, f"Added {product.name} to your cart.")
    if request.POST.get("buy_now"):
        return redirect("checkout")
    return redirect(request.POST.get("next") or request.META.get("HTTP_REFERER") or "cart")


@require_POST
def cart_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.POST.get("remove"):
        Cart(request).remove(pk)
    else:
        wanted = int(request.POST.get("qty", 1) or 0)
        got = Cart(request).set(product, wanted)
        if got < wanted:
            messages.warning(request, f"Only {product.stock} of {product.name} available.")
    return redirect("cart")


def cart_view(request):
    lines = Cart(request).lines()
    return render(request, "shop/cart.html", {"lines": lines, "subtotal": sum(l["total"] for l in lines)})


def checkout(request):
    cart = Cart(request)
    lines = cart.lines()
    if not lines:
        messages.info(request, "Your cart is empty.")
        return redirect("home")
    subtotal = sum(l["total"] for l in lines)

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            if d["payment_method"] == Order.MPESA:
                try:
                    d["phone"] = mpesa.normalize_phone(d["phone"])
                except mpesa.MpesaError as e:
                    form.add_error("phone", str(e))
            if not form.errors:
                try:
                    order = place_order(
                        [(l["product"].pk, l["qty"]) for l in lines],
                        user=request.user if request.user.is_authenticated else None, **d)
                except OutOfStock as e:
                    messages.error(request, f"Stock changed while you were shopping: {e} Please update your cart.")
                    return redirect("cart")
                cart.clear()
                remember_order(request, order)
                if order.payment_method == Order.MPESA:
                    send_stk(request, order)
                    return redirect(order.get_absolute_url())
                return redirect(order.get_absolute_url() + "?new=1")
    else:
        initial = {}
        if request.user.is_authenticated:
            last = request.user.orders.first()
            initial = {"full_name": request.user.get_full_name(), "email": request.user.email,
                       "phone": last.phone if last else ""}
        form = CheckoutForm(initial=initial)

    shop = ShopSettings.get()
    return render(request, "shop/checkout.html", {
        "form": form, "lines": lines, "subtotal": subtotal,
        "free_over": shop.free_delivery_over, "delivery_fee": shop.delivery_fee,
    })


# =====================================================================
# 4. Orders, M-Pesa, WhatsApp
# =====================================================================

def send_stk(request, order):
    if not mpesa.is_configured():
        return  # demo mode — the order page shows a Simulate button instead
    try:
        order.checkout_request_id = mpesa.stk_push(order.phone, order.total, order.number)
        order.mpesa_message = "Payment prompt sent. Enter your M-Pesa PIN on your phone."
        messages.success(request, "Check your phone and enter your M-Pesa PIN to pay.")
    except (mpesa.MpesaError, Exception) as e:  # network errors etc.
        order.mpesa_message = f"Could not send prompt: {e}"[:255]
        messages.error(request, "We couldn't send the M-Pesa prompt. Tap 'Send payment prompt again' below.")
    order.save()


def order_detail(request, number):
    order = get_object_or_404(Order, number=number)
    if not can_view_order(request, order):
        messages.info(request, "Enter your order number and phone to view that order.")
        return redirect("track_order")
    return render(request, "shop/order.html", {
        "order": order, "items": order.items.all(), "wa_order_link": whatsapp_order_link(order),
        "demo_mode": not mpesa.is_configured(), "is_new": request.GET.get("new") == "1",
    })


@require_POST
def order_pay(request, number):
    order = get_object_or_404(Order, number=number)
    if not can_view_order(request, order):
        return HttpResponseForbidden()
    if order.status == Order.PENDING:
        phone = request.POST.get("phone") or order.phone
        try:
            order.phone = mpesa.normalize_phone(phone)
        except mpesa.MpesaError as e:
            messages.error(request, str(e))
            return redirect(order.get_absolute_url())
        order.payment_method = Order.MPESA
        send_stk(request, order)
    return redirect(order.get_absolute_url())


@require_POST
def order_simulate_payment(request, number):
    """Demo mode only (no M-Pesa keys set): pretend the customer paid."""
    order = get_object_or_404(Order, number=number)
    if mpesa.is_configured() or not can_view_order(request, order):
        return HttpResponseForbidden()
    order.mark_paid(receipt="DEMO" + order.number[2:], message="Demo payment (M-Pesa keys not set yet)")
    messages.success(request, "Demo payment recorded.")
    return redirect(order.get_absolute_url())


def order_status_json(request, number):
    """Polled by the order page every few seconds while waiting for M-Pesa."""
    order = get_object_or_404(Order, number=number)
    if not can_view_order(request, order):
        raise Http404
    failed = False
    if (order.status == Order.PENDING and order.checkout_request_id and mpesa.is_configured()
            and timezone.now() - order.updated > timedelta(seconds=20)):
        try:
            code, desc = mpesa.stk_query(order.checkout_request_id)
            if code == "0":
                order.mark_paid(message=desc)
            elif code is not None:
                order.mpesa_message = desc[:255]
                order.checkout_request_id = ""
                order.save()
                failed = True
        except Exception:
            pass
    return JsonResponse({"status": order.status, "label": order.get_status_display(),
                         "message": order.mpesa_message, "failed": failed or not order.checkout_request_id})


@csrf_exempt
@require_POST
def mpesa_callback(request):
    """Safaricom calls this URL with the payment result."""
    try:
        data = mpesa.parse_callback(json.loads(request.body))
    except (ValueError, AttributeError):
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Bad request"})
    order = Order.objects.filter(checkout_request_id=data["checkout_request_id"]).first() \
        if data["checkout_request_id"] else None
    if order:
        if data["result_code"] == "0":
            order.mark_paid(receipt=data["receipt"], message=data["result_desc"])
        else:
            order.mpesa_message = data["result_desc"][:255]
            order.checkout_request_id = ""
            order.save()
    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})


def track_order(request):
    form = TrackOrderForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        number = form.cleaned_data["number"].strip().upper()
        digits = "".join(c for c in form.cleaned_data["phone"] if c.isdigit())[-9:]
        order = Order.objects.filter(number=number).first()
        if order and digits and order.phone.endswith(digits):
            remember_order(request, order)
            return redirect(order.get_absolute_url())
        form.add_error(None, "We couldn't find an order with that number and phone.")
    return render(request, "shop/track.html", {"form": form})


# =====================================================================
# 5. Customer accounts (optional — guests can still buy)
# =====================================================================

def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome! Your account is ready.")
        return redirect(request.GET.get("next") or "account")
    return render(request, "shop/auth.html", {"form": form, "mode": "signup"})


class CustomerLoginView(LoginView):
    template_name = "shop/auth.html"
    authentication_form = EmailLoginForm
    extra_context = {"mode": "login"}

    def get_success_url(self):
        if self.request.user.is_staff and not self.get_redirect_url():
            return "/dashboard/"
        return super().get_success_url()


def account(request):
    if not request.user.is_authenticated:
        return redirect("login")
    guest_numbers = request.session.get("my_orders", [])
    orders = Order.objects.filter(Q(user=request.user) | Q(number__in=guest_numbers)).distinct()
    return render(request, "shop/account.html", {"orders": orders})


# =====================================================================
# 6. Owner dashboard (staff accounts only)
# =====================================================================

def owner_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.path}")
        if not request.user.is_staff:
            messages.error(request, "That area is for the shop owner only.")
            return redirect("home")
        return view(request, *args, **kwargs)
    return wrapper


@owner_required
def dash_home(request):
    now = timezone.localtime()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    paid = Order.objects.filter(status__in=PAID_STATUSES)
    return render(request, "dashboard/home.html", {
        "sales_today": paid.filter(created__gte=today).aggregate(s=Sum("total"))["s"] or 0,
        "orders_today": Order.objects.filter(created__gte=today).exclude(status=Order.CANCELLED).count(),
        "sales_month": paid.filter(created__gte=month).aggregate(s=Sum("total"))["s"] or 0,
        "to_process": Order.objects.filter(status=Order.PAID).count(),
        "awaiting": Order.objects.filter(status=Order.PENDING).count(),
        "low_stock": low_stock_qs()[:10],
        "recent": Order.objects.all()[:8],
        "product_count": Product.objects.filter(is_active=True).count(),
    })


@owner_required
def dash_products(request):
    products = Product.objects.select_related("category").order_by("name")
    q = request.GET.get("q", "").strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(brand__icontains=q))
    f = request.GET.get("filter")
    if f == "low":
        products = low_stock_qs()
    elif f == "hidden":
        products = products.filter(is_active=False)
    elif f == "offers":
        products = products.filter(old_price__gt=F("price"))
    return render(request, "dashboard/products.html", {"products": products, "q": q, "filter": f})


@owner_required
def dash_product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        p = form.save()
        messages.success(request, f"Saved “{p.name}”.")
        if request.POST.get("add_another"):
            return redirect("dash_product_new")
        return redirect("dash_products")
    return render(request, "dashboard/product_form.html", {"form": form, "product": product})


@owner_required
@require_POST
def dash_product_stock(request, pk):
    product = get_object_or_404(Product, pk=pk)
    try:
        if request.POST.get("add"):
            product.stock = max(0, product.stock + int(request.POST["add"]))
        else:
            product.stock = max(0, int(request.POST.get("stock", product.stock)))
        product.save(update_fields=["stock", "updated"])
        messages.success(request, f"{product.name}: stock is now {product.stock}.")
    except ValueError:
        messages.error(request, "Enter a whole number.")
    return redirect(request.META.get("HTTP_REFERER") or "dash_products")


@owner_required
@require_POST
def dash_product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    name = product.name
    product.delete()
    messages.success(request, f"Deleted “{name}”. Past orders still show it.")
    return redirect("dash_products")


@owner_required
def dash_orders(request):
    orders = Order.objects.annotate(n=Sum("items__quantity"))
    status = request.GET.get("status", "")
    if status:
        orders = orders.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        orders = orders.filter(Q(number__icontains=q) | Q(full_name__icontains=q) | Q(phone__icontains=q))
    counts = dict(Order.objects.values_list("status").annotate(c=Count("id")))
    tabs = [("", "All", sum(counts.values()))] + [(k, v, counts.get(k, 0)) for k, v in Order.STATUS_CHOICES]
    return render(request, "dashboard/orders.html", {"orders": orders[:300], "status": status, "q": q, "tabs": tabs})


@owner_required
def dash_order(request, number):
    order = get_object_or_404(Order, number=number)
    form = OrderStatusForm(request.POST or None, instance=order)
    if request.method == "POST":
        if order.status == Order.CANCELLED:
            messages.error(request, "This order was cancelled and its stock returned. Create a new order instead.")
        elif form.is_valid():
            new = form.cleaned_data["status"]
            if new == Order.CANCELLED:
                Order.objects.get(pk=order.pk).cancel()
                messages.success(request, f"Order {order.number} cancelled — items returned to stock.")
            else:
                form.save()
                messages.success(request, f"Order {order.number} marked “{order.get_status_display()}”.")
        return redirect("dash_order", number=order.number)
    shop = ShopSettings.get()
    cust = "".join(c for c in order.phone if c.isdigit())
    if cust.startswith("0"):
        cust = "254" + cust[1:]
    msg = quote(f"Hello {order.full_name.split(' ')[0]}, this is {shop.shop_name} about your order {order.number}.")
    return render(request, "dashboard/order.html", {"order": order, "form": form, "items": order.items.all(),
                                                    "wa_customer": f"https://wa.me/{cust}?text={msg}"})


@owner_required
def dash_categories(request, pk=None):
    editing = get_object_or_404(Category, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, instance=editing)
    if request.method == "POST":
        if request.POST.get("delete") and editing:
            editing.delete()
            messages.success(request, "Category deleted. Its products are now uncategorised.")
            return redirect("dash_categories")
        if form.is_valid():
            form.save()
            messages.success(request, "Category saved.")
            return redirect("dash_categories")
    cats = Category.objects.annotate(n=Count("products"))
    return render(request, "dashboard/categories.html", {"categories": cats, "form": form, "editing": editing})


@owner_required
def dash_settings(request):
    form = ShopSettingsForm(request.POST or None, instance=ShopSettings.get())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Shop settings saved.")
        return redirect("dash_settings")
    return render(request, "dashboard/settings.html", {"form": form, "mpesa_ready": mpesa.is_configured()})
