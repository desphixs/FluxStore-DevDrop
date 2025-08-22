from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings 

class User(AbstractUser):
    email = models.EmailField(unique=True) 
    username = models.CharField(unique=True, max_length=50)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def save(self, *args, **kwargs):
        # If no username is set, fallback to email as username
        if not self.username and self.email:
            self.username = self.email
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
