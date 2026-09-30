"""
python manage.py setup_shop            → creates the owner account (from OWNER_EMAIL / OWNER_PASSWORD) if missing
python manage.py setup_shop --demo     → also adds sample categories & products (only if the shop has no products)
Safe to run on every deploy.
"""
import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from shop.models import Category, Product, ShopSettings


def img(photo_id):
    return f"https://images.unsplash.com/photo-{photo_id}?w=800&q=70&auto=format&fit=crop"


CATEGORIES = [
    ("Laptops", "1531297484001-80022131f5a1"),
    ("MacBooks", "1611186871348-b1ce696e52c9"),
    ("Desktops & Monitors", "1593640408182-31c70c8268f5"),
    ("Mice & Keyboards", "1551739440-5dd934d3a94a"),
    ("Chargers & Power", "1583863788434-e58a36330cf0"),
    ("Accessories", "1577375729078-820d5283031c"),
]

# (category, name, brand, specs, price, old_price, stock, photo, featured, description)
PRODUCTS = [
    ("Laptops", "HP EliteBook 840 G6", "HP", "Core i5 8th Gen · 8GB RAM · 256GB SSD · 14\" FHD", 38500, 45000, 6,
     "1531297484001-80022131f5a1", True, "Slim business laptop with backlit keyboard, fingerprint reader and all-day battery.\nComes with charger and 6 months warranty."),
    ("Laptops", "Acer Aspire 5", "Acer", "Core i5 12th Gen · 8GB RAM · 512GB SSD · 15.6\"", 62000, None, 4,
     "1522199755839-a2bacb67c546", False, "Great all-rounder for students and office work. Full-size keyboard with number pad."),
    ("Laptops", "Lenovo ThinkPad T480", "Lenovo", "Core i5 · 16GB RAM · 512GB SSD · 14\"", 35000, None, 2,
     "1484788984921-03950022c9ef", False, "Durable ThinkPad with the famous keyboard. Ex-UK, thoroughly tested."),
    ("MacBooks", "MacBook Air M1 13\"", "Apple", "Apple M1 · 8GB · 256GB SSD · Retina", 95000, 105000, 3,
     "1541807084-5c52b6b3adef", True, "Silent, fanless and fast. Up to 18 hours of battery life."),
    ("MacBooks", "MacBook Air M2 13.6\"", "Apple", "Apple M2 · 8GB · 256GB SSD · Liquid Retina", 128000, None, 5,
     "1611186871348-b1ce696e52c9", True, "Thin new design, MagSafe charging and a brighter display."),
    ("MacBooks", "MacBook Pro 14\" M3", "Apple", "Apple M3 · 8GB · 512GB SSD · XDR display", 215000, None, 2,
     "1525547719571-a2d4ac8945e2", False, "Pro performance for editing, design and development."),
    ("MacBooks", "MacBook Pro 13\" (Intel i5)", "Apple", "Core i5 · 8GB · 256GB SSD · Touch Bar", 68000, None, 0,
     "1597673030062-0a0f1a801a31", False, "Ex-UK MacBook Pro in excellent condition."),
    ("Desktops & Monitors", "Apple iMac 24\" M1", "Apple", "Apple M1 · 8GB · 256GB · 4.5K Retina", 165000, None, 1,
     "1494173853739-c21f58b16055", False, "All-in-one desktop with keyboard and mouse included."),
    ("Desktops & Monitors", "Core i7 Desktop Tower", "Vertex Build", "Core i7 · 16GB RAM · 1TB SSD · Windows 11", 72000, None, 3,
     "1587302912306-cf1ed9c33146", False, "Powerful desktop for office, design or light gaming. Monitor sold separately."),
    ("Desktops & Monitors", "24\" Full HD Monitor", "Samsung", "24\" IPS · 1920×1080 · HDMI & VGA", 16500, 18500, 8,
     "1547658718-1cdaa0852790", False, "Slim-bezel monitor, great as a second screen for your laptop."),
    ("Mice & Keyboards", "Logitech M185 Wireless Mouse", "Logitech", "2.4GHz USB receiver · 12-month battery", 1500, None, 25,
     "1527864550417-7fd91fc51a46", True, "Compact, reliable wireless mouse. Plug and play."),
    ("Mice & Keyboards", "Logitech G305 Gaming Mouse", "Logitech", "Wireless · HERO sensor · 6 buttons", 5500, None, 7,
     "1527814050087-3793815479db", False, "Lightweight wireless gaming mouse with long battery life."),
    ("Mice & Keyboards", "Wireless Keyboard & Mouse Combo", "Logitech", "Full-size keyboard · Wireless mouse · 1 receiver", 3200, 3800, 12,
     "1551739440-5dd934d3a94a", True, "Quiet keys and a single USB receiver for both."),
    ("Mice & Keyboards", "Mechanical Keyboard", "Redragon", "Blue switches · RGB backlight · USB", 6500, None, 3,
     "1636036824578-d0d300a4effb", False, "Satisfying typing and gaming keyboard with RGB lighting."),
    ("Chargers & Power", "Apple 30W USB-C Power Adapter", "Apple", "USB-C · Fast charge · MacBook Air & iPhone", 5800, None, 10,
     "1583863788434-e58a36330cf0", True, "Original Apple adapter. Cable sold separately."),
    ("Chargers & Power", "65W USB-C Laptop Charger", "Universal", "65W PD · Works with most USB-C laptops", 3500, None, 15,
     "1636015856875-00ce4b89433d", False, "Charges USB-C laptops, tablets and phones."),
    ("Chargers & Power", "HP 65W Laptop Charger (Blue Pin)", "HP", "19.5V 3.33A · 4.5mm blue tip", 2500, None, 2,
     "1756043827116-5764e6d23d85", False, "Replacement charger for most HP laptops with the blue-tip connector."),
    ("Chargers & Power", "Universal Travel Adapter", "Universal", "UK/EU/US plugs · 2 USB ports", 1200, None, 20,
     "1517320069935-381614f8c1e5", False, "One adapter for travel anywhere."),
    ("Accessories", "64GB USB Flash Drive", "SanDisk", "USB 3.0 · Up to 100MB/s", 1200, 1500, 30,
     "1779896412420-d37179cdffb9", False, "Fast, pocket-size storage for documents and media."),
    ("Accessories", "Laptop Accessories Starter Kit", "Vertex", "Sleeve · Mouse · Cleaning kit · USB hub", 4500, None, 5,
     "1577375729078-820d5283031c", False, "Everything you need with a new laptop, in one pack."),
]


class Command(BaseCommand):
    help = "Create the owner account and (optionally) demo products."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true", help="Add sample categories and products if the shop is empty")

    def handle(self, *args, **opts):
        ShopSettings.get()
        email, password = os.environ.get("OWNER_EMAIL", "").lower(), os.environ.get("OWNER_PASSWORD", "")
        if email and password:
            user, created = User.objects.get_or_create(username=email, defaults={"email": email, "first_name": "Owner"})
            if created:
                user.set_password(password)
            user.is_staff = user.is_superuser = True
            user.save()
            self.stdout.write(f"Owner account {'created' if created else 'ready'}: {email}")
        else:
            self.stdout.write("Set OWNER_EMAIL and OWNER_PASSWORD to create the owner account.")

        if opts["demo"] and not Product.objects.exists():
            cats = {}
            for i, (name, photo) in enumerate(CATEGORIES):
                cats[name], _ = Category.objects.get_or_create(name=name, defaults={"image_url": img(photo), "sort_order": i})
            for cat, name, brand, specs, price, old, stock, photo, featured, desc in PRODUCTS:
                Product.objects.create(category=cats[cat], name=name, brand=brand, short_specs=specs, price=price,
                                       old_price=old, stock=stock, image_url=img(photo), is_featured=featured,
                                       description=desc)
            self.stdout.write(self.style.SUCCESS(f"Added {len(PRODUCTS)} demo products in {len(CATEGORIES)} categories."))
