from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegisterView, PhoneTokenObtainPairView, MeView,
    IdeaConfigurationViewSet, ProjectViewSet, ListedProjectViewSet,
    WalletView, NotificationViewSet, PartnerViewSet, AnnouncementViewSet, ChangePasswordView, GenerateReferralView,
    TelegramWebhookView, RegisterTopupTelegramMessageView,
    ApproveTopupView, RejectTopupView,
)

router = DefaultRouter()
router.register(r'configs', IdeaConfigurationViewSet, basename='config')
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'listings', ListedProjectViewSet, basename='listing')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'partners', PartnerViewSet, basename='partner')
router.register(r'announcements', AnnouncementViewSet, basename='announcement')

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', PhoneTokenObtainPairView.as_view(), name='login'),
    path('auth/me/', MeView.as_view(), name='me'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('auth/generate-referral/', GenerateReferralView.as_view(), name='generate_referral'),
    path('wallet/topup/', WalletView.as_view(), name='wallet_topup'),
    path('approve-topup/', ApproveTopupView.as_view(), name='approve_topup'),
    path('reject-topup/', RejectTopupView.as_view(), name='reject_topup'),
    path('register-topup-message/', RegisterTopupTelegramMessageView.as_view(), name='register_topup_message'),
    path('telegram/webhook/', TelegramWebhookView.as_view(), name='telegram_webhook'),
    path('', include(router.urls)),
]
