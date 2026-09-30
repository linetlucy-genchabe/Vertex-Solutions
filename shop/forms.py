from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from .models import Category, Order, Product, ShopSettings


class CheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=100, label="Full name")
    phone = forms.CharField(max_length=20, label="Phone number", help_text="M-Pesa prompt goes to this number")
    email = forms.EmailField(required=False, label="Email (optional)")
    delivery_method = forms.ChoiceField(choices=Order.DELIVERY_CHOICES, widget=forms.RadioSelect, initial=Order.PICKUP)
    address = forms.CharField(max_length=255, required=False, label="Delivery location",
                              widget=forms.TextInput(attrs={"placeholder": "Estate, street, building, landmark"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Notes (optional)")
    payment_method = forms.ChoiceField(choices=Order.PAYMENT_CHOICES, widget=forms.RadioSelect, initial=Order.MPESA)

    def clean(self):
        data = super().clean()
        if data.get("delivery_method") == Order.DELIVERY and not data.get("address"):
            self.add_error("address", "Tell us where to deliver.")
        return data


class SignupForm(forms.Form):
    full_name = forms.CharField(max_length=100)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, min_length=6)
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with this email already exists. Log in instead.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password") != data.get("password2"):
            self.add_error("password2", "Passwords don't match.")
        return data

    def save(self):
        d = self.cleaned_data
        first, _, last = d["full_name"].partition(" ")
        return User.objects.create_user(username=d["email"], email=d["email"], password=d["password"],
                                        first_name=first, last_name=last)


class EmailLoginForm(AuthenticationForm):
    username = forms.CharField(label="Email")

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class TrackOrderForm(forms.Form):
    number = forms.CharField(max_length=12, label="Order number")
    phone = forms.CharField(max_length=20, label="Phone used at checkout")


# ---------- Owner dashboard ----------

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "category", "brand", "short_specs", "price", "old_price", "stock", "low_stock_alert",
                  "image", "image_url", "description", "is_active", "is_featured"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}
        labels = {"old_price": "Old price (for offers)", "image": "Upload photo", "image_url": "…or photo link",
                  "is_active": "Show in shop", "is_featured": "Feature on home page",
                  "low_stock_alert": "Low-stock alert at"}


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "image_url", "sort_order"]
        labels = {"image_url": "Photo link (optional)", "sort_order": "Position"}


class OrderStatusForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["status"]


class ShopSettingsForm(forms.ModelForm):
    class Meta:
        model = ShopSettings
        fields = "__all__"
