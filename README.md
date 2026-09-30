# Vertex Solutions — online store

A Django store for **Vertex Solutions**, Dynamic Mall, Shop SL26. Customers can shop for laptops, MacBooks, desktops and accessories, then pay by **M-Pesa (STK push)** or send the order on **WhatsApp**. The owner runs everything from a simple **dashboard** on the site.

## Where things are (one app, few files)

| File | What's in it |
|---|---|
| `shop/models.py` | All data: shop settings, categories, products, orders, and the stock-deduction logic |
| `shop/views.py` | Every page: shop, cart, checkout, orders, M-Pesa, accounts, owner dashboard |
| `config/urls.py` | Every web address |
| `shop/forms.py` | Checkout, sign-up and dashboard forms |
| `shop/mpesa.py` | M-Pesa Daraja STK push |
| `templates/` | HTML pages (`shop/` for customers, `dashboard/` for the owner) |
| `static/css/style.css` | All styling (shades of blue) |
| `shop/tests.py` | Automated tests (`python manage.py test shop`) |

## Run it on your computer

```bash
pip install -r requirements.txt
python manage.py migrate
OWNER_EMAIL=owner@example.com OWNER_PASSWORD=demo12345 python manage.py setup_shop --demo
python manage.py runserver
```
Then open http://127.0.0.1:8000. To use the dashboard, sign in at `/login/` with the owner email and go to `/dashboard/`.

`--demo` adds 20 sample products with photos. The prices are only placeholders, so the owner should edit them or delete the products.

## How the owner uses it

- **Add product** (dashboard → Add product): enter a name, category, price and stock, then upload a photo or paste a photo link. Put the old price in **Old price** and the item shows as an offer with a -% badge.
- **Stock** goes down automatically when a customer places an order. It is reserved at that moment, so two people can't buy the last item. You can change stock numbers straight from the Products list.
- **Low-stock alerts**: the dashboard lists items at or below their alert level (default 3; you can change it in Settings or per product). An orange badge in the menu shows how many need attention.
- **Orders**: move each order through Paid → Dispatched/Ready → Completed. **Cancelled** puts the items back into stock. There are also one-tap WhatsApp and Call buttons for the customer.
- **Settings**: shop name, location, phone, WhatsApp number, delivery fee and the free-delivery threshold.

## Deploy on Railway

1. Push this folder to GitHub and create a Railway project from the repo. Add a **PostgreSQL** database (this sets `DATABASE_URL`).
2. Add a **Volume** mounted at `/data`, so uploaded photos survive redeploys.
3. Copy the variables from `.env.example` into the service's Variables and fill them in.
4. Deploy. The `Procfile` runs migrations, creates the owner account and starts the site.
5. Custom domain: in Railway → Settings → Domains, add `yourname.co.ke`, then create the CNAME it shows at your domain registrar (e.g. Truehost/HostPinnacle DNS).

## M-Pesa (STK push)

Until keys are added, the site runs in **demo mode**: no real prompt is sent, and the order page shows a *Simulate payment* button.

1. Create an app at https://developer.safaricom.co.ke and test with sandbox shortcode `174379` and the sandbox passkey.
2. For real money, apply to **Go Live** with the shop's Paybill or Till. Safaricom then gives you a production passkey.
3. Set `MPESA_ENV=production`, the keys, `MPESA_SHORTCODE` (Paybill number, or the Store number for a Till), `MPESA_TILL_NUMBER` (Till only), `MPESA_PASSKEY`, and `MPESA_CALLBACK_URL=https://yourdomain/mpesa/callback/`.

The order turns **Paid** by itself when Safaricom confirms the payment. If the confirmation is slow, the order page checks with Safaricom directly.
