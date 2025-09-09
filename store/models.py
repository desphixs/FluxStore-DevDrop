from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django_ckeditor_5.fields import CKEditor5Field
from django.db.models import Avg, Count
from django.utils import timezone

from shortuuid.django_fields import ShortUUIDField

class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    image = models.FileField(upload_to="categoryImages", null=True, blank=True)
    slug = models.SlugField(max_length=255, null=True, blank=True)
    description = models.CharField(blank=True, max_length=255, null=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    is_active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    trending = models.BooleanField(default=False)

    def products(self):
        return Product.objects.filter(status=Product.ProductStatus.PUBLISHED, category=self)

    def subcategories(self):
        return Category.objects.filter(parent=self, is_active=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Product(models.Model):
    class ProductStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='products', limit_choices_to={'role': 'VENDOR'})
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = CKEditor5Field('Text', config_name='default')
    status = models.CharField(max_length=10, choices=ProductStatus.choices, default=ProductStatus.DRAFT)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.uuid}")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def product_images(self):
        return self.images.filter(product=self)
    
    @property
    def primary_image(self):
        return self.images.filter(is_primary=True).first()

    def primary_item(self):
        return self.variations.filter(product=self, is_active=True, is_primary=True).first()
    
    def total_reviews(self):
        return self.reviews.count()

    def average_rating(self):
        avg = self.reviews.aggregate(avg=Avg('rating'))['avg'] or 0
        return round(avg, 1)  # 4.0 etc.

    def average_rating_int(self):
        return int(round(self.average_rating()))


class VariationCategory(models.Model):
    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='variation_categories', limit_choices_to={'role': 'VENDOR'})
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = 'Variation Categories'
        unique_together = ('vendor', 'name')

    def __str__(self):
        return f"{self.name} ({self.vendor.vendor_profile.business_name})"

class VariationValue(models.Model):
    category = models.ForeignKey(VariationCategory, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=100)

    class Meta:
        unique_together = ('category', 'value')

    def __str__(self):
        return f"{self.category.name}: {self.value}"



class ProductVariation(models.Model):
    LABEL_CHOICES = (
        ('Hot', 'Hot'),
        ('New', 'New'),
        ('Sale', 'Sale'),
        ('Bestseller', 'Bestseller'),
        ('Limited', 'Limited'),
        ('Featured', 'Featured'),
        ('Exclusive', 'Exclusive'),
        ('Coming Soon', 'Coming Soon'),
        ('Back in Stock', 'Back in Stock'),
        ('Trending', 'Trending'),
        ('Clearance', 'Clearance'),
        ('Popular', 'Popular'),
        ('Gift', 'Gift'),
    )

    SHOW_DISCOUNT_TYPE = (
        ('price', 'Show Discount in Price'),
        ('percentage', 'Show Discount in Percentage'),
        ('none', 'Do Not Show Discount'),
    )

    product = models.ForeignKey("Product", on_delete=models.CASCADE, related_name='variations')
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    regular_price = models.DecimalField(max_digits=10, decimal_places=2)
    show_regular_price = models.BooleanField(default=False)
    show_discount_type = models.CharField(choices=SHOW_DISCOUNT_TYPE, default="none", max_length=100)
    # Deal fields
    deal_active = models.BooleanField(default=False)
    deal_starts_at = models.DateTimeField(null=True, blank=True)
    deal_ends_at = models.DateTimeField(null=True, blank=True)

    stock_quantity = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")
    variations = models.ManyToManyField("VariationValue")

    weight = models.DecimalField(max_digits=6, decimal_places=2, help_text="Weight in KG")
    length = models.DecimalField(max_digits=6, decimal_places=2, help_text="Length in CM")
    height = models.DecimalField(max_digits=6, decimal_places=2, help_text="Height in CM")
    width = models.DecimalField(max_digits=6, decimal_places=2, help_text="Width in CM")

    # NEW: product label (Hot, New, Sale, etc.)
    label = models.CharField(
        max_length=50,
        choices=LABEL_CHOICES,
        default='New'
    )

    class Meta:
        ordering = ['sale_price']

    def discount_amount(self):
        """How much money is saved"""
        if self.regular_price > self.sale_price:
            return self.regular_price - self.sale_price
        return 0

    def discount_percentage(self):
        """Discount in %"""
        if self.regular_price > self.sale_price:
            return round((self.discount_amount() / self.regular_price) * 100, 2)
        return 0
    
    @property
    def label_color(self):
        return LABEL_COLORS.get(self.label, "bg-gray-300 text-black")

    def __str__(self):
        variation_str = ", ".join([str(v.value) for v in self.variations.all()])
        return f"{self.product.name} ({variation_str})"
    
    @property
    def is_current_deal(self):
        """True if deal is active and now is between start and end."""
        if not self.deal_active or not self.deal_ends_at:
            return False
        now = timezone.now()
        if self.deal_starts_at:
            return self.deal_starts_at <= now <= self.deal_ends_at
        return now <= self.deal_ends_at



class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    product_variation = models.ForeignKey(ProductVariation, on_delete=models.SET_NULL, null=True, blank=True, related_name='images')
    image = models.FileField(upload_to='product_images/')
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"Image for {self.product.name}"

class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    class Meta:
        unique_together = ('product', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"Review for {self.product.name} by {self.user.email}"
LABEL_COLORS = {
        'Hot': 'bg-red-500 text-white',
        'New': 'bg-green-500 text-white',
        'Sale': 'bg-yellow-500 text-black',
        'Bestseller': 'bg-purple-500 text-white',
        'Limited': 'bg-pink-500 text-white',
        'Featured': 'bg-indigo-500 text-white',
        'Exclusive': 'bg-blue-500 text-white',
        'Coming Soon': 'bg-gray-500 text-white',
        'Back in Stock': 'bg-teal-500 text-white',
        'Trending': 'bg-orange-500 text-white',
        'Clearance': 'bg-red-700 text-white',
        'Popular': 'bg-emerald-500 text-white',
        'Gift': 'bg-fuchsia-500 text-white',
    }

