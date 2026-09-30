import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .models import Category, Order, Product, ShopSettings


class StoreTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Laptops")
        self.laptop = Product.objects.create(category=self.cat, name="HP EliteBook", price=40000, stock=3)
        self.mouse = Product.objects.create(category=self.cat, name="Mouse", price=1500, stock=10)
        self.owner = User.objects.create_user("owner@x.com", "owner@x.com", "pass1234", is_staff=True)

    def checkout(self, **extra):
        data = {"full_name": "Jane Doe", "phone": "0712345678", "delivery_method": "pickup",
                "payment_method": "mpesa", **extra}
        return self.client.post("/checkout/", data)

    def test_pages_load(self):
        for url in ["/", "/shop/", "/category/laptops/", f"/product/{self.laptop.slug}/", "/cart/", "/track/",
                    "/login/", "/signup/", "/shop/?q=hp", "/shop/?offers=1"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_order_deducts_stock_and_clears_cart(self):
        self.client.post(f"/cart/add/{self.laptop.pk}/", {"qty": 2})
        self.client.post(f"/cart/add/{self.mouse.pk}/", {"qty": 1})
        r = self.checkout()
        order = Order.objects.get()
        self.assertRedirects(r, order.get_absolute_url())
        self.assertEqual(order.total, 81500)
        self.assertEqual(order.phone, "254712345678")
        self.laptop.refresh_from_db(); self.mouse.refresh_from_db()
        self.assertEqual((self.laptop.stock, self.mouse.stock), (1, 9))
        self.assertEqual(self.client.session["cart"], {})

    def test_cannot_add_more_than_stock(self):
        self.client.post(f"/cart/add/{self.laptop.pk}/", {"qty": 50})
        self.assertEqual(self.client.session["cart"][str(self.laptop.pk)], 3)

    def test_out_of_stock_at_checkout_is_blocked(self):
        self.client.post(f"/cart/add/{self.laptop.pk}/", {"qty": 3})
        Product.objects.filter(pk=self.laptop.pk).update(stock=1)  # someone else bought
        r = self.checkout()
        self.assertRedirects(r, "/cart/")
        self.assertFalse(Order.objects.exists())
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.stock, 1)

    def test_delivery_fee_and_free_delivery(self):
        s = ShopSettings.get(); s.delivery_fee = 300; s.free_delivery_over = 20000; s.save()
        self.client.post(f"/cart/add/{self.mouse.pk}/", {"qty": 1})
        self.checkout(delivery_method="delivery", address="Kilimani")
        self.assertEqual(Order.objects.get().total, 1800)
        self.client.post(f"/cart/add/{self.laptop.pk}/", {"qty": 1})
        self.checkout(delivery_method="delivery", address="Kilimani")
        self.assertEqual(Order.objects.first().delivery_fee, 0)

    def test_whatsapp_order_links_to_whatsapp(self):
        self.client.post(f"/cart/add/{self.mouse.pk}/", {"qty": 2})
        r = self.checkout(payment_method="whatsapp")
        order = Order.objects.get()
        page = self.client.get(r.url)
        self.assertContains(page, "https://wa.me/")
        self.assertContains(page, order.number)

    def test_demo_payment_marks_paid(self):
        self.client.post(f"/cart/add/{self.mouse.pk}/", {"qty": 1})
        self.checkout()
        order = Order.objects.get()
        self.client.post(f"/order/{order.number}/simulate/")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.PAID)

    def test_strangers_cannot_view_order(self):
        self.client.post(f"/cart/add/{self.mouse.pk}/", {"qty": 1})
        self.checkout()
        order = Order.objects.get()
        other = self.client_class()
        self.assertRedirects(other.get(order.get_absolute_url()), "/track/")
        r = other.post("/track/", {"number": order.number, "phone": "0712 345 678"})
        self.assertRedirects(r, order.get_absolute_url())

    def test_mpesa_callback_marks_paid(self):
        self.client.post(f"/cart/add/{self.mouse.pk}/", {"qty": 1})
        self.checkout()
        order = Order.objects.get()
        order.checkout_request_id = "ws_CO_123"; order.save()
        body = {"Body": {"stkCallback": {"CheckoutRequestID": "ws_CO_123", "ResultCode": 0, "ResultDesc": "OK",
                "CallbackMetadata": {"Item": [{"Name": "MpesaReceiptNumber", "Value": "QK12ABC"}, {"Name": "Amount", "Value": 1500}]}}}}
        self.client.post("/mpesa/callback/", json.dumps(body), content_type="application/json")
        order.refresh_from_db()
        self.assertEqual((order.status, order.mpesa_receipt), (Order.PAID, "QK12ABC"))

    def test_cancel_returns_stock(self):
        self.client.post(f"/cart/add/{self.laptop.pk}/", {"qty": 2})
        self.checkout()
        order = Order.objects.get()
        self.client.login(username="owner@x.com", password="pass1234")
        self.client.post(f"/dashboard/orders/{order.number}/", {"status": "cancelled"})
        self.client.post(f"/dashboard/orders/{order.number}/", {"status": "cancelled"})  # twice: no double refund
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.stock, 3)

    def test_dashboard_is_owner_only(self):
        self.assertEqual(self.client.get("/dashboard/").status_code, 302)
        User.objects.create_user("c@x.com", "c@x.com", "pass1234")
        self.client.login(username="c@x.com", password="pass1234")
        self.assertRedirects(self.client.get("/dashboard/"), "/")

    def test_owner_adds_product_and_updates_stock(self):
        self.client.login(username="owner@x.com", password="pass1234")
        for url in ["/dashboard/", "/dashboard/products/", "/dashboard/products/new/", "/dashboard/orders/",
                    "/dashboard/categories/", "/dashboard/settings/", "/dashboard/products/?filter=low"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        r = self.client.post("/dashboard/products/new/", {"name": "Dell Charger", "category": self.cat.pk,
                             "price": 2500, "stock": 4, "is_active": "on"})
        self.assertRedirects(r, "/dashboard/products/")
        p = Product.objects.get(name="Dell Charger")
        self.client.post(f"/dashboard/products/{p.pk}/stock/", {"add": 6})
        p.refresh_from_db()
        self.assertEqual(p.stock, 10)
        self.assertContains(self.client.get("/shop/?q=dell"), "Dell Charger")

    def test_low_stock_alert(self):
        self.client.login(username="owner@x.com", password="pass1234")
        r = self.client.get("/dashboard/")
        self.assertContains(r, "HP EliteBook")  # stock 3 = default alert level
        self.assertNotContains(r, ">Mouse<")

    def test_signup_and_account_orders(self):
        self.client.post("/signup/", {"full_name": "Ann K", "email": "ann@x.com", "password": "secret12", "password2": "secret12"})
        self.client.post(f"/cart/add/{self.mouse.pk}/", {"qty": 1})
        self.checkout()
        self.assertEqual(Order.objects.get().user.username, "ann@x.com")
        self.assertContains(self.client.get("/account/"), Order.objects.get().number)
