"""All database tables for the store live in this one file."""
import secrets

from django.conf import settings
from django.core.cache import cache
from django.db import models, transaction
from django.db.models import F
from django.urls import reverse
from django.utils.text import slugify


class ShopSettings(models.Model):
    """One row only. The owner edits this from Dashboard → Shop settings."""

    shop_name = models.CharField(max_length=80, default="Vertex Solutions")
    tagline = models.CharField(max_length=140, default="Computers, laptops & accessories you can trust")
    location = models.CharField(max_length=140, default="Dynamic Mall, Shop SL26, Nairobi")
    phone = models.CharField(max_length=20, default="0700 000 000", help_text="Shown on the site for calls")
    whatsapp_number = models.CharField(
        max_length=20, default="254700000000",
        help_text="International format without + or spaces, e.g. 254712345678",
    )
    email = models.EmailField(blank=True)
    delivery_fee = models.PositiveIntegerField(default=300, help_text="Flat delivery fee in KES (pickup is free)")
    free_delivery_over = models.PositiveIntegerField(default=20000, help_text="Orders at or above this total get free delivery. 0 = never")
    low_stock_default = models.PositiveIntegerField(default=3, help_text="Alert when stock falls to this number or below")

    class Meta:
        verbose_name_plural = "Shop settings"

    def __str__(self):
        return self.shop_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete("shop_settings")

    @classmethod
    def get(cls):
        obj = cache.get("shop_settings")
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set("shop_settings", obj, 60)
        return obj


class Category(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True, blank=True)
    image_url = models.URLField(blank=True, help_text="Optional photo link for the category tile")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("category", args=[self.slug])


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    brand = models.CharField(max_length=60, blank=True)
    short_specs = models.CharField(max_length=160, blank=True, help_text="One line, e.g. 'Core i5 · 8GB RAM · 256GB SSD'")
    description = models.TextField(blank=True)
    price = models.PositiveIntegerField(help_text="Selling price in KES")
    old_price = models.PositiveIntegerField(null=True, blank=True, help_text="Fill this to show the item as ON OFFER (crossed-out price)")
    stock = models.PositiveIntegerField(default=0)
    low_stock_alert = models.PositiveIntegerField(null=True, blank=True, help_text="Leave blank to use the shop default")
    image = models.ImageField(upload_to="products/", blank=True)
    image_url = models.URLField(blank=True, help_text="Or paste a photo link instead of uploading")
    is_active = models.BooleanField(default=True, help_text="Untick to hide from the shop")
    is_featured = models.BooleanField(default=False, help_text="Show on the home page")
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:150] or "item"
            slug, n = base, 2
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("product", args=[self.slug])

    @property
    def photo(self):
        if self.image:
            return self.image.url
        return self.image_url

    @property
    def on_offer(self):
        return bool(self.old_price and self.old_price > self.price)

    @property
    def discount_percent(self):
        if not self.on_offer:
            return 0
        return round((self.old_price - self.price) * 100 / self.old_price)

    @property
    def alert_level(self):
        if self.low_stock_alert is not None:
            return self.low_stock_alert
        return ShopSettings.get().low_stock_default

    @property
    def is_low_stock(self):
        return 0 < self.stock <= self.alert_level

    @property
    def in_stock(self):
        return self.stock > 0


def new_order_number():
    return "VS" + secrets.token_hex(3).upper()


class Order(models.Model):
    PENDING, PAID, DISPATCHED, COMPLETED, CANCELLED = "pending", "paid", "dispatched", "completed", "cancelled"
    STATUS_CHOICES = [
        (PENDING, "Awaiting payment"),
        (PAID, "Paid"),
        (DISPATCHED, "Dispatched / Ready for pickup"),
        (COMPLETED, "Completed"),
        (CANCELLED, "Cancelled"),
    ]
    MPESA, WHATSAPP = "mpesa", "whatsapp"
    PAYMENT_CHOICES = [(MPESA, "M-Pesa (STK push)"), (WHATSAPP, "Order via WhatsApp")]
    PICKUP, DELIVERY = "pickup", "delivery"
    DELIVERY_CHOICES = [(PICKUP, "Pick up at the shop"), (DELIVERY, "Deliver to me")]

    number = models.CharField(max_length=12, unique=True, default=new_order_number, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    delivery_method = models.CharField(max_length=10, choices=DELIVERY_CHOICES, default=PICKUP)
    address = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default=MPESA)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    subtotal = models.PositiveIntegerField(default=0)
    delivery_fee = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    # M-Pesa details
    checkout_request_id = models.CharField(max_length=80, blank=True, db_index=True)
    mpesa_receipt = models.CharField(max_length=30, blank=True)
    mpesa_message = models.CharField(max_length=255, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse("order_detail", args=[self.number])

    @property
    def is_open(self):
        return self.status not in (self.COMPLETED, self.CANCELLED)

    def cancel(self):
        """Cancel the order and put the items back into stock (only once)."""
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=self.pk)
            if order.status == Order.CANCELLED:
                return
            for item in order.items.select_related("product"):
                if item.product_id:
                    Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
            order.status = Order.CANCELLED
            order.save(update_fields=["status", "updated"])
            self.status = Order.CANCELLED

    def mark_paid(self, receipt="", message=""):
        if self.status == Order.PENDING:
            self.status = Order.PAID
        if receipt:
            self.mpesa_receipt = receipt
        if message:
            self.mpesa_message = message[:255]
        self.save()


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=150)  # kept even if the product is later deleted
    price = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField(default=1)

    @property
    def line_total(self):
        return self.price * self.quantity


class OutOfStock(Exception):
    pass


def place_order(cart_lines, **order_fields):
    """
    Create an order and deduct stock in one safe step.
    cart_lines: list of (product_id, quantity). Raises OutOfStock if anything ran out.
    """
    shop = ShopSettings.get()
    with transaction.atomic():
        ids = [pid for pid, _ in cart_lines]
        products = {p.pk: p for p in Product.objects.select_for_update().filter(pk__in=ids, is_active=True)}
        subtotal = 0
        for pid, qty in cart_lines:
            p = products.get(pid)
            if not p or p.stock < qty:
                name = p.name if p else "An item"
                left = p.stock if p else 0
                raise OutOfStock(f"{name} — only {left} left in stock.")
            subtotal += p.price * qty

        fee = 0
        if order_fields.get("delivery_method") == Order.DELIVERY:
            fee = shop.delivery_fee
            if shop.free_delivery_over and subtotal >= shop.free_delivery_over:
                fee = 0

        order = Order.objects.create(subtotal=subtotal, delivery_fee=fee, total=subtotal + fee, **order_fields)
        for pid, qty in cart_lines:
            p = products[pid]
            OrderItem.objects.create(order=order, product=p, name=p.name, price=p.price, quantity=qty)
            Product.objects.filter(pk=pid).update(stock=F("stock") - qty)
        return order
