from django.db import models
from django.conf import settings
from django.utils.text import slugify
from shortuuid.django_fields import ShortUUIDField
from django_ckeditor_5.fields import CKEditor5Field

class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    is_active = models.BooleanField(default=True)

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
        return ProductImage.objects.filter(product=self)
    
    def image(self):
        return ProductImage.objects.filter(product=self, is_primary=True).first()

    def item(self):
        return ProductVariation.objects.filter(product=self, is_active=True).first()

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
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variations')
    variations = models.ManyToManyField(VariationValue)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    class Meta:
        ordering = ['price']

    def __str__(self):
        variation_str = ", ".join([str(v.value) for v in self.variations.all()])
        return f"{self.product.name} ({variation_str})"

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
