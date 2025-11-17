from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.html import format_html
from decimal import Decimal
from django.db import transaction
from .models import User, IdeaConfiguration, Project, ListedProject, Notification, TopUpTransaction, Partner, Promocode, PromocodeUsage, Announcement


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("id", "phone_number", "full_name", "workplace", "balance", "is_investor", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_investor")
    ordering = ("-date_joined",)
    search_fields = ("phone_number",)

    fieldsets = (
        (None, {"fields": ("phone_number", "password", "full_name", "workplace")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "is_investor", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
        ("Wallet", {"fields": ("balance", "is_subscribed", "referral_code", "referred_by")}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'password1', 'password2', 'is_staff', 'is_superuser'),
        }),
    )


@admin.register(IdeaConfiguration)
class IdeaConfigurationAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "industry", "investment", "created_at")
    search_fields = ("industry", "investment", "owner__phone_number")
    list_filter = ("created_at",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "project_name", "created_at")
    search_fields = ("project_name", "owner__phone_number")
    list_filter = ("created_at",)


@admin.register(ListedProject)
class ListedProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "funding_sought", "equity_offered", "created_at")
    search_fields = ("project__project_name",)
    list_filter = ("created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "type", "title", "timestamp", "read")
    list_filter = ("type", "read", "timestamp")
    search_fields = ("user__phone_number", "title")


@admin.register(TopUpTransaction)
class TopUpTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "amount", "cashback", "promo_code", "promo_bonus", "is_active", "created_at", "activated_at", "receipt_link")
    list_filter = ("is_active", "created_at", "activated_at")
    search_fields = ("user__phone_number",)
    readonly_fields = ("created_at", "activated_at")

    actions = ["approve_topups"]

    def receipt_link(self, obj):
        if obj.receipt:
            return format_html('<a href="{}" target="_blank">{}\u2197\ufe0f</a>', obj.receipt.url, obj.receipt.name.split('/')[-1])
        return "—"
    receipt_link.short_description = "Receipt"

    def approve_topups(self, request, queryset):
        """Approve selected top-ups: credit user balance and mark as active."""
        approved = 0
        with transaction.atomic():
            for tx in queryset.select_related("user"):
                if tx.is_active:
                    continue
                has_used = bool(tx.promo_code) and PromocodeUsage.objects.filter(user=tx.user, promocode=tx.promo_code).exists()
                promo_bonus = Decimal(tx.promo_bonus) if tx.promo_code and not has_used else Decimal('0.00')
                total = (Decimal(tx.amount) + Decimal(tx.cashback) + promo_bonus).quantize(Decimal('0.01'))
                user = tx.user
                user.balance = (Decimal(user.balance) + total).quantize(Decimal('0.01'))
                user.save(update_fields=["balance"])
                tx.is_active = True
                tx.activated_at = timezone.now()
                tx.save(update_fields=["is_active", "activated_at"])
                if tx.promo_code and not has_used:
                    PromocodeUsage.objects.create(user=user, promocode=tx.promo_code)
                Notification.objects.create(
                    user=user,
                    type='success',
                    title='Top-up approved',
                    message=f'+{tx.amount} qo\'shildi, +{tx.cashback} cashback, +{promo_bonus} promo. Balans yangilandi.'
                )
                approved += 1
        self.message_user(request, f"Approved {approved} top-up transaction(s).")
    approve_topups.short_description = "Approve selected top-ups"

    def save_model(self, request, obj, form, change):
        """If admin toggles is_active from False->True, credit the user's balance and set activated_at."""
        if change and obj.pk and 'is_active' in form.changed_data:
            prev = TopUpTransaction.objects.get(pk=obj.pk)
            if not prev.is_active and obj.is_active:
                with transaction.atomic():
                    has_used = bool(obj.promo_code) and PromocodeUsage.objects.filter(user=obj.user, promocode=obj.promo_code).exists()
                    promo_bonus = Decimal(obj.promo_bonus) if obj.promo_code and not has_used else Decimal('0.00')
                    total = (Decimal(obj.amount) + Decimal(obj.cashback) + promo_bonus).quantize(Decimal('0.01'))
                    user = obj.user
                    user.balance = (Decimal(user.balance) + total).quantize(Decimal('0.01'))
                    user.save(update_fields=["balance"])
                    obj.activated_at = timezone.now()
                    super().save_model(request, obj, form, change)
                    if obj.promo_code and not has_used:
                        PromocodeUsage.objects.create(user=user, promocode=obj.promo_code)
                    Notification.objects.create(
                        user=user,
                        type='success',
                        title='Top-up approved',
                        message=f'+{obj.amount} qo\'shildi, +{obj.cashback} cashback, +{promo_bonus} promo. Balans yangilandi.'
                    )
                return
        super().save_model(request, obj, form, change)


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "contact_person", "contact_phone", "website", "created_at")
    search_fields = ("name", "contact_person", "contact_phone")
    list_filter = ("created_at",)


@admin.register(Promocode)
class PromocodeAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "percent", "is_active", "created_at")
    search_fields = ("code",)
    list_filter = ("is_active", "created_at")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "is_active", "deadline", "created_at")
    list_filter = ("is_active", "created_at", "deadline")
    search_fields = ("title",)
