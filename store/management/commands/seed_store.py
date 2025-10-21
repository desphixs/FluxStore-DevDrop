# seed_store.py
# Place at: <app>/management/commands/seed_store.py
from __future__ import annotations

import random
import string
from decimal import Decimal
from datetime import timedelta
from typing import List, Dict, Tuple

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.utils.text import slugify

# --- Import your apps' models ---
from store.models import (
    Category,
    Product,
    VariationCategory,
    VariationValue,
    ProductVariation,
    ProductImage,     
    ProductReview,
)
from order.models import (
    Order,
    OrderItem,
)
from customer.models import (
    Wishlist,
    WishlistItem,
)
from userauths.models import (
    UserProfile,
    VendorProfile,
    Address,
)

# ------------------------------
# Data pools
# ------------------------------
CATEGORIES = [
    "Fashion",
    "Electronics",
    "Appliances",
    "Phones & Tablets",
    "Health & Beauty",
    "Home & Office",
    "Supermarket",
    "Gaming",
]

FIRST_NAMES = [
    "Jennifer", "Michael", "Aisha", "Emeka", "Daniel", "Sophia", "Oluwaseun", "Chiamaka",
    "David", "Fatima", "Grace", "Samuel", "Vivian", "Ibrahim", "Kelechi", "Moses",
    "Isabella", "Anthony", "Gloria", "Chioma", "Ahmed", "Peter", "Ngozi", "Tunde",
    "Mary", "John", "Hassan", "Rita", "Blessing", "Mark", "Cynthia", "Ifeanyi",
]
LAST_NAMES = [
    "Anderson", "Okafor", "Owolabi", "Johnson", "Ogunleye", "Adebayo", "Mohammed", "Ali",
    "Nwosu", "Ibrahim", "Williams", "Oladipo", "Brown", "Garcia", "Ikechukwu", "Thomas",
    "Adams", "Usman", "Eze", "Campbell", "Onyeka", "Bello", "Smith", "Torres",
]

# Per-category name seeds (short banks; mixed brands/models)
PRODUCT_NAME_BANK: Dict[str, Tuple[List[str], List[str]]] = {
    "Fashion": (["VOIDEREUX", "AeroFit", "UrbanEdge", "PrimeWear", "BoldLine"],
                ["Cotton Tee", "Denim Jacket", "Slim Jeans", "Hoodie", "Polo", "Chino Pants"]),
    "Electronics": (["SoundMax", "VoltX", "ApexTech", "NeuroCore", "Skyline"],
                    ["Bluetooth Speaker", "Smart TV", "Noise Cancelling Headphones", "Home Theater", "Projector"]),
    "Appliances": (["HomeChef", "CoolBreeze", "RapidWash", "PureAir", "ThermoPro"],
                   ["Air Fryer", "Microwave Oven", "Washing Machine", "Refrigerator", "Air Purifier"]),
    "Phones & Tablets": (["Nova", "PixelWave", "Orion", "ZenTab", "Aura"],
                         ["Android Phone", "5G Smartphone", "Tablet 10\"", "Tablet Pro 11\"", "Fold Phone"]),
    "Health & Beauty": (["GlowLab", "PureSkin", "FreshMint", "VitalEase", "DermaLux"],
                        ["Vitamin C Serum", "Face Cleanser", "Moisturizer", "Body Lotion", "Toothbrush Electric"]),
    "Home & Office": (["ErgoFlex", "ComfyHome", "SteelFrame", "BrightLite", "Organix"],
                      ["Office Chair", "LED Desk Lamp", "Standing Desk", "Bookshelf", "Storage Box"]),
    "Supermarket": (["DailyFresh", "ChefChoice", "GrainGold", "SnackBox", "PureDrop"],
                    ["Basmati Rice 5kg", "Vegetable Oil 3L", "Sweet Corn (Pack)", "Spaghetti (Carton)", "Tomato Paste"]),
    "Gaming": (["ProX", "ShadowCore", "NeoByte", "Omega", "Strafe"],
               ["Gamepad", "Gaming Mouse", "Mechanical Keyboard", "Headset 7.1", "4K Capture Card"]),
}

LABEL_CHOICES = [l for l, _ in ProductVariation.LABEL_CHOICES]
SHOW_DISCOUNT_TYPE = [v for v, _ in ProductVariation.SHOW_DISCOUNT_TYPE]

LOREM = (
    "Built for everyday use with solid materials. Smooth experience, great value, and backed by our 1-year warranty."
)

# ------------------------------
# Helpers
# ------------------------------
def rand_money(low: int, high: int) -> Decimal:
    return Decimal(str(random.randint(low, high)))

def random_sku(prefix: str = "SKU") -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{suffix}"

def ensure_vendor_variation_taxonomy(vendor) -> Tuple[VariationCategory, VariationCategory]:
    """Create (or fetch) two standard variation categories per vendor: Color & Size."""
    color_vc, _ = VariationCategory.objects.get_or_create(vendor=vendor, name="Color")
    size_vc, _ = VariationCategory.objects.get_or_create(vendor=vendor, name="Size")

    for val in ["Black", "White", "Blue", "Red"]:
        VariationValue.objects.get_or_create(category=color_vc, value=val)
    for val in ["S", "M", "L"]:
        VariationValue.objects.get_or_create(category=size_vc, value=val)
    return color_vc, size_vc

def pick_two_variation_values(vendor) -> List[VariationValue]:
    color_vc = VariationCategory.objects.get(vendor=vendor, name="Color")
    size_vc = VariationCategory.objects.get(vendor=vendor, name="Size")
    color = random.choice(list(color_vc.values.all()))
    size = random.choice(list(size_vc.values.all()))
    return [color, size]

def build_product_name(cat: Category) -> str:
    brands, items = PRODUCT_NAME_BANK.get(cat.name, ([], []))
    brand = random.choice(brands) if brands else "BrandX"
    item = random.choice(items) if items else "Item"
    return f"{brand} {item}"

def unique_business_name(base: str) -> str:
    """Ensure VendorProfile.business_name (unique=True) does not clash."""
    name = base
    i = 1
    while VendorProfile.objects.filter(business_name=name).exists():
        i += 1
        name = f"{base} #{i}"
    return name

# ------------------------------
# Seeder
# ------------------------------
class Command(BaseCommand):
    help = "Seed categories, users (buyers & vendors), products, variations, reviews, orders, and wishlists."

    def add_arguments(self, parser):
        
        parser.add_argument("--users", type=int, default=20,
                            help="Total users to create (min 15). Roughly 40% will be vendors.")
        parser.add_argument("--orders", type=int, default=30,
                            help="Total orders to create (min 15).")
        parser.add_argument("--products", type=int, default=50,
                            help="Total products to create across categories (min 24).")
        parser.add_argument("--per-category", type=int, default=5,
                            help="Minimum products per category (default 5). Pass 3 if you want exactly 3.")
        parser.add_argument("--max-per-category", type=int, default=20,
                            help="Hard cap for products per single category (default 20).")
        parser.add_argument("--reviews-max", type=int, default=3,
                            help="Max reviews per product (random 0..N).")
        parser.add_argument("--no-wishlist", action="store_true",
                            help="Skip creating wishlists & wishlist items.")

    def handle(self, *args, **opts):
        random.seed(42)  

        
        users_target = max(15, int(opts["users"]))
        orders_target = max(15, int(opts["orders"]))
        products_target = max(24, int(opts["products"]))
        per_cat_min = max(3, int(opts["per_category"]))
        per_cat_cap = max(5, int(opts["max_per_category"]))
        reviews_max = max(0, int(opts["reviews_max"]))
        make_wishlist = not bool(opts["no_wishlist"])

        self.stdout.write(self.style.WARNING("⚙️  Starting seed..."))
        self.stdout.write(f"Users target: {users_target}, Products target: {products_target}, Orders target: {orders_target}")

        
        categories = self._seed_categories()
        self.stdout.write(self.style.SUCCESS(f"✅ Categories ready: {len(categories)}"))

        
        buyers, vendors = self._seed_users(users_target)
        self.stdout.write(self.style.SUCCESS(f"✅ Users created: buyers={len(buyers)}, vendors={len(vendors)}"))

        
        products = self._seed_products(
            categories, vendors, target=products_target,
            per_cat_min=per_cat_min, per_cat_cap=per_cat_cap,
        )
        self.stdout.write(self.style.SUCCESS(f"✅ Products created: {len(products)} (with primary variations)"))

        
        if reviews_max > 0:
            total_reviews = self._seed_reviews(products, buyers, reviews_max)
            self.stdout.write(self.style.SUCCESS(f"✅ Reviews created: {total_reviews}"))
        else:
            self.stdout.write("⏭️  Skipping reviews (reviews-max=0)")

        
        orders = self._seed_orders(orders_target, buyers, products)
        self.stdout.write(self.style.SUCCESS(f"✅ Orders created: {len(orders)}"))

        
        if make_wishlist:
            wl_count = self._seed_wishlists(buyers, products)
            self.stdout.write(self.style.SUCCESS(f"✅ Wishlists updated: {wl_count} users added items"))
        else:
            self.stdout.write("⏭️  Skipping wishlists (--no-wishlist)")

        self.stdout.write(self.style.WARNING("🏁 Seeding complete."))

    
    
    
    def _seed_categories(self) -> List[Category]:
        
        unique_names: List[str] = []
        for nm in CATEGORIES:
            if nm not in unique_names:
                unique_names.append(nm)

        out: List[Category] = []
        for name in unique_names:
            obj, created = Category.objects.get_or_create(
                name=name,
                defaults={
                    "slug": slugify(name),
                    "description": f"{name} products",
                    "is_active": True,
                    "featured": False,
                    "trending": False,
                },
            )
            out.append(obj)
            self.stdout.write(f"  • Category: {name} ({'created' if created else 'existing'})")
        return out

    
    
    
    def _seed_users(self, total_users: int) -> Tuple[List[object], List[object]]:
        User = get_user_model()
        buyers: List[object] = []
        vendors: List[object] = []

        target_vendors = max(6, int(total_users * 0.4))  
        target_buyers = total_users - target_vendors

        self.stdout.write("👤 Creating users...")
        used_emails = set(User.objects.values_list("email", flat=True))

        def unique_email(first: str, last: str) -> str:
            base = f"{first}.{last}".lower().replace(" ", "")
            for i in range(500):
                dom = random.choice(["example.com", "mail.test", "shopdemo.dev"])
                email = f"{base}{'' if i == 0 else str(i)}@{dom}"
                if email not in used_emails:
                    used_emails.add(email)
                    return email
            
            return f"{base}.{random.randint(1000,9999)}@example.com"

        
        while len(vendors) < target_vendors:
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            email = unique_email(first, last)
            try:
                with transaction.atomic():
                    u = User.objects.create_user(
                        email=email,
                        username=email,
                        password="password123",
                        role=User.Role.VENDOR,
                        first_name=first,
                        last_name=last,
                    )
                    UserProfile.objects.get_or_create(user=u)

                    
                    base_name = f"{last} {first} Store"
                    business_name = unique_business_name(base_name)

                    VendorProfile.objects.create(
                        user=u,
                        business_name=business_name,
                        contact_email=email,
                        business_phone=f"+23480{random.randint(10000000,99999999)}",
                        business_address=f"{random.randint(12,199)} Broad Street, Lagos",
                        business_description="Quality goods, fast delivery.",
                        currency="USD",
                        country="NG",
                        is_open=True,
                    )
                    ensure_vendor_variation_taxonomy(u)
                    vendors.append(u)
                    self.stdout.write(f"  • VENDOR {u.email}")
            except IntegrityError as e:
                self.stdout.write(self.style.ERROR(f"    × Vendor unique clash: {e}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    × Vendor create failed: {e}"))

        
        while len(buyers) < target_buyers:
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            email = unique_email(first, last)
            try:
                with transaction.atomic():
                    u = User.objects.create_user(
                        email=email,
                        username=email,
                        password="password123",
                        role=User.Role.BUYER,
                        first_name=first,
                        last_name=last,
                    )
                    prof, _ = UserProfile.objects.get_or_create(user=u)
                    
                    Address.objects.get_or_create(
                        profile=prof,
                        address_type=Address.AddressType.SHIPPING,
                        defaults={
                            "full_name": f"{first} {last}",
                            "phone": f"+23481{random.randint(10000000,99999999)}",
                            "street_address": f"{random.randint(10,250)} Market Road",
                            "city": random.choice(["Lagos", "Abuja", "Port Harcourt", "Ibadan", "Kano"]),
                            "state": random.choice(["Lagos", "FCT", "Rivers", "Oyo", "Kano"]),
                            "postal_code": str(random.randint(100001, 900001)),
                            "country": "Nigeria",
                            "is_default": True,
                        },
                    )
                    buyers.append(u)
                    self.stdout.write(f"  • BUYER  {u.email}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    × Buyer create failed: {e}"))

        return buyers, vendors

    
    
    
    def _seed_products(
        self,
        categories: List[Category],
        vendors: List[object],
        target: int,
        per_cat_min: int,
        per_cat_cap: int,
    ) -> List[Product]:
        self.stdout.write("🛒 Creating products...")

        
        n_cat = len(categories)
        base_each = max(per_cat_min, target // n_cat)
        remainder = max(0, target - (base_each * n_cat))

        counts: Dict[int, int] = {}
        for idx in range(n_cat):
            count = min(per_cat_cap, base_each + (1 if idx < remainder else 0))
            counts[idx] = count

        created_products: List[Product] = []

        for idx, cat in enumerate(categories):
            want = counts[idx]
            self.stdout.write(f"  • Category {cat.name}: target {want}")

            for _ in range(want):
                vendor = random.choice(vendors)
                name = build_product_name(cat)
                try:
                    with transaction.atomic():
                        p = Product.objects.create(
                            vendor=vendor,
                            category=cat,
                            name=name,
                            description=LOREM,
                            status=Product.ProductStatus.PUBLISHED,
                            is_featured=random.choice([True, False, False]),
                        )

                        
                        sale = rand_money(15, 120)
                        reg = sale + rand_money(3, 25)  
                        pv = ProductVariation.objects.create(
                            product=p,
                            sale_price=sale,
                            regular_price=reg,
                            shipping_price=rand_money(2, 15),
                            show_regular_price=True,
                            show_discount_type=random.choice(SHOW_DISCOUNT_TYPE),
                            deal_active=random.choice([True, False, False]),
                            deal_starts_at=timezone.now() if random.choice([True, False]) else None,
                            deal_ends_at=timezone.now() + timedelta(days=random.randint(3, 14)),
                            stock_quantity=random.randint(10, 120),
                            sku=random_sku(prefix=cat.name.split()[0][:3].upper()),
                            is_active=True,
                            is_primary=True,
                            weight=Decimal("%.2f" % random.uniform(0.2, 8.0)),
                            length=Decimal("%.2f" % random.uniform(5.0, 60.0)),
                            height=Decimal("%.2f" % random.uniform(2.0, 40.0)),
                            width=Decimal("%.2f" % random.uniform(3.0, 50.0)),
                            label=random.choice(LABEL_CHOICES),
                        )
                        
                        try:
                            ensure_vendor_variation_taxonomy(vendor)
                            for vv in pick_two_variation_values(vendor):
                                pv.variations.add(vv)
                        except Exception as ve:
                            self.stdout.write(self.style.ERROR(f"      × Variation link failed: {ve}"))

                        created_products.append(p)
                        if (len(created_products) % 10) == 0:
                            self.stdout.write(f"    … {len(created_products)} products so far")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    × Product failed ({name}): {e}"))

        return created_products

    
    
    
    def _seed_reviews(self, products: List[Product], buyers: List[object], reviews_max: int) -> int:
        self.stdout.write("💬 Creating reviews…")
        total = 0
        for p in products:
            k = random.randint(0, reviews_max)
            if not buyers:
                break
            sampled_buyers = random.sample(buyers, k=min(k, len(buyers)))
            for u in sampled_buyers:
                try:
                    with transaction.atomic():
                        ProductReview.objects.create(
                            product=p,
                            user=u,
                            rating=random.randint(3, 5),
                            comment=random.choice([
                                "Works as expected.",
                                "Great quality for the price!",
                                "Solid build, fast delivery.",
                                "Decent, could be better packaging.",
                            ]),
                        )
                        total += 1
                except Exception as e:
                    
                    self.stdout.write(self.style.WARNING(f"    ! Review skipped: {e}"))
        return total

    
    
    
    def _seed_orders(self, orders_target: int, buyers: List[object], products: List[Product]) -> List[Order]:
        self.stdout.write("📦 Creating orders…")
        out: List[Order] = []
        if not buyers or not products:
            self.stdout.write(self.style.ERROR("    × Need buyers and products to create orders"))
            return out

        pvars = list(ProductVariation.objects.filter(is_active=True))
        if not pvars:
            self.stdout.write(self.style.ERROR("    × No active product variations available"))
            return out

        for i in range(orders_target):
            buyer = random.choice(buyers)
            try:
                with transaction.atomic():
                    
                    profile = buyer.profile
                    addr = profile.addresses.filter(address_type=Address.AddressType.SHIPPING).first()
                    if not addr:
                        addr = Address.objects.create(
                            profile=profile,
                            address_type=Address.AddressType.SHIPPING,
                            full_name=f"{buyer.first_name} {buyer.last_name}",
                            phone=f"+23480{random.randint(10000000,99999999)}",
                            street_address=f"{random.randint(10,250)} Unity Road",
                            city=random.choice(["Lagos", "Abuja", "PH"]),
                            state=random.choice(["Lagos", "FCT", "Rivers"]),
                            postal_code=str(random.randint(100001, 900001)),
                            country="Nigeria",
                            is_default=True,
                        )

                    order = Order.objects.create(
                        buyer=buyer,
                        address=addr,
                        status=random.choice(list(Order.OrderStatus.values)),
                        payment_status=random.choice(["UNPAID", "PAID", "FAILED"]),
                    )

                    
                    n_items = random.randint(1, 4)
                    chosen_vars = random.sample(pvars, k=min(n_items, len(pvars)))
                    for pv in chosen_vars:
                        qty = random.randint(1, min(3, max(1, pv.stock_quantity)))
                        oi = OrderItem.objects.create(
                            order=order,
                            product_variation=pv,
                            vendor=pv.product.vendor,
                            quantity=qty,
                            price=pv.sale_price,
                        )
                        
                        for vv in pv.variations.all():
                            oi.variation_values.add(vv)
                        oi.recompute_line_totals()
                        oi.save(update_fields=["line_subtotal_net"])

                    
                    order.set_order_id_if_missing()
                    order.recompute_item_totals_from_items()
                    order.shipping_fee = rand_money(2, 20)
                    order.recalc_total()
                    order.save()

                    out.append(order)
                    if ((i + 1) % 5) == 0:
                        self.stdout.write(f"    … {i+1}/{orders_target} orders")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    × Order failed: {e}"))
        return out

    
    
    
    def _seed_wishlists(self, buyers: List[object], products: List[Product]) -> int:
        self.stdout.write("📝 Creating wishlists…")
        count = 0
        for u in buyers:
            try:
                wl, _ = Wishlist.objects.get_or_create(user=u)
                if random.random() < 0.55:  
                    for p in random.sample(products, k=min(3, len(products))):
                        pv = p.variations.filter(is_primary=True).first()
                        if not pv:
                            continue
                        WishlistItem.objects.get_or_create(
                            wishlist=wl,
                            product=p,
                            product_variation=pv,
                        )
                    count += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"    ! Wishlist skip for {u.id}: {e}"))
        return count
