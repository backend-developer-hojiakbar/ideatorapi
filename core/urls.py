from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegisterView, PhoneTokenObtainPairView, MeView,
    IdeaConfigurationViewSet, ProjectViewSet, ListedProjectViewSet,
    WalletView, NotificationViewSet, PartnerViewSet
)

router = DefaultRouter()
router.register(r'configs', IdeaConfigurationViewSet, basename='config')
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'listings', ListedProjectViewSet, basename='listing')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'partners', PartnerViewSet, basename='partner')

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', PhoneTokenObtainPairView.as_view(), name='login'),
    path('auth/me/', MeView.as_view(), name='me'),
    path('wallet/topup/', WalletView.as_view(), name='wallet_topup'),
    path('', include(router.urls)),
]
