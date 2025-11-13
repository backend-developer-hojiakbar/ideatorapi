from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, phone_number: str, password: str | None = None, **extra):
        if not phone_number:
            raise ValueError('Phone number is required')
        user = self.model(phone_number=phone_number, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number: str, password: str, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        if extra.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(phone_number, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    phone_number = models.CharField(max_length=32, unique=True)
    full_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_subscribed = models.BooleanField(default=False)

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.phone_number


class IdeaConfiguration(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='configs')
    industry = models.CharField(max_length=200)
    investment = models.CharField(max_length=200)
    idea_topic = models.CharField(max_length=255, blank=True)
    brief_info = models.TextField(blank=True)
    complexity = models.CharField(max_length=100)
    business_model = models.JSONField(default=list)  # list of strings
    is_golden_ticket = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Project(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    config = models.ForeignKey(IdeaConfiguration, on_delete=models.SET_NULL, null=True, blank=True)
    project_name = models.CharField(max_length=255)
    description = models.TextField()
    data = models.JSONField(default=dict)  # full generated idea payload
    created_at = models.DateTimeField(auto_now_add=True)


class ListedProject(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='listing')
    funding_sought = models.DecimalField(max_digits=14, decimal_places=2)
    equity_offered = models.DecimalField(max_digits=5, decimal_places=2)  # percent
    pitch = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    TYPE_CHOICES = (
        ('success', 'success'),
        ('error', 'error'),
        ('info', 'info'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, default='info')
    title = models.CharField(max_length=255)
    message = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    read = models.BooleanField(default=False)


class TopUpTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='topups')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    cashback = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=False)
    receipt = models.FileField(upload_to='receipts/', null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
