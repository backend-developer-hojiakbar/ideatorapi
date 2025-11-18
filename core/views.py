from decimal import Decimal
import secrets
from django.db import transaction
from django.utils import timezone
from django.conf import settings
import requests
import json
import hmac
import hashlib
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache

from .models import User, IdeaConfiguration, Project, ListedProject, Notification, TopUpTransaction, Partner, Announcement, PromocodeUsage
from .serializers import (
    RegisterSerializer, PhoneTokenObtainPairSerializer, UserSerializer,
    IdeaConfigurationSerializer, ProjectSerializer, ListedProjectSerializer,
    NotificationSerializer, TopUpSerializer, PartnerSerializer, AnnouncementSerializer, ChangePasswordSerializer
)


class AllowAnyCreateMixin:
    def get_permissions(self):
        if self.request.method.lower() == 'post':
            return [permissions.AllowAny()]
        return super().get_permissions()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class PhoneTokenObtainPairView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PhoneTokenObtainPairSerializer


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = request.user
        old_password = ser.validated_data['old_password']
        new_password = ser.validated_data['new_password']
        if not user.check_password(old_password):
            return Response({'detail': 'Eski parol noto\'g\'ri'}, status=400)
        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'status': 'ok'})


class GenerateReferralView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.referral_code:
            while True:
                code = secrets.token_hex(4).upper()
                if not User.objects.filter(referral_code=code).exists():
                    user.referral_code = code
                    user.save(update_fields=['referral_code'])
                    break
        return Response({'referral_code': user.referral_code})


class IdeaConfigurationViewSet(viewsets.ModelViewSet):
    serializer_class = IdeaConfigurationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return IdeaConfiguration.objects.filter(owner=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=['post'], url_path='start')
    def start_project(self, request):
        """Deduct fixed fee (10000) from user balance and create project from provided payload."""
        FEE = Decimal('10000')
        user = request.user
        if user.balance < FEE:
            return Response({'detail': 'Insufficient balance'}, status=400)
        data = request.data
        project_name = data.get('project_name')
        description = data.get('description')
        project_data = data.get('data', {})
        config_id = data.get('config')
        with transaction.atomic():
            user.balance = Decimal(user.balance) - FEE
            user.save(update_fields=['balance'])
            project = Project.objects.create(
                owner=user,
                config=IdeaConfiguration.objects.filter(id=config_id, owner=user).first() if config_id else None,
                project_name=project_name or 'Unnamed Project',
                description=description or '',
                data=project_data or {},
            )
            Notification.objects.create(
                user=user,
                type='success',
                title='New project started',
                message=f'Fee {FEE} deducted. Project {project.project_name} created.'
            )
        return Response(ProjectSerializer(project).data, status=201)


class ListedProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ListedProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ListedProject.objects.filter(project__owner=self.request.user)

    def perform_create(self, serializer):
        project = Project.objects.get(id=self.request.data.get('project'))
        if project.owner != self.request.user:
            raise PermissionError('Not your project')
        serializer.save(project=project)

    def list(self, request, *args, **kwargs):
        """Public listing endpoint: show all listings if ?all=1 else only own."""
        if request.query_params.get('all') == '1':
            if not request.user.is_authenticated or not getattr(request.user, 'is_investor', False):
                return Response({'detail': 'Investor huquqi talab qilinadi'}, status=403)
            qs = ListedProject.objects.select_related('project', 'project__owner').all().order_by('-created_at')
        else:
            qs = self.get_queryset().order_by('-created_at')
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = ListedProjectSerializer(page, many=True)
            return self.get_paginated_response(ser.data)
        ser = ListedProjectSerializer(qs, many=True)
        return Response(ser.data)


def _approve_topup_transaction(tx: TopUpTransaction):
    """Approve and activate a TopUpTransaction: credit balance and mark is_active, set activated_at, record promo usage, notify user."""
    if tx.is_active:
        return False
    with transaction.atomic():
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
    return True




class WalletView(generics.GenericAPIView):
    serializer_class = TopUpSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def post(self, request):
        """Create a pending top-up transaction. Admin approval will credit balance with 1% cashback (+ optional promo bonus)."""
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        amount = ser.validated_data['amount']
        user = request.user
        cashback = (amount * Decimal('0.01')).quantize(Decimal('0.01'))
        promo = ser.validated_data.get('promo')
        promo_bonus = Decimal('0.00')
        if promo:
            promo_bonus = (amount * Decimal(promo.percent) / Decimal('100')).quantize(Decimal('0.01'))
        receipt_file = ser.validated_data.get('receipt')
        with transaction.atomic():
            topup = TopUpTransaction.objects.create(
                user=user,
                amount=amount,
                cashback=cashback,
                promo_code=promo if promo else None,
                promo_bonus=promo_bonus,
                is_active=False,
                receipt=receipt_file if receipt_file else None,
            )
            message = f"{amount} so'm to'ldirish so'rovi yuborildi. Admin tasdiqlagach balansingizga +{amount} va +{cashback} cashback qo'shiladi."
            if promo:
                message += f" Promo: {promo.code} orqali +{promo_bonus} bonus qo'shiladi."
            Notification.objects.create(
                user=user,
                type='info',
                title='Top-up requested',
                message=message
            )
        # Telegram yuborish frontend orqali amalga oshiriladi
        # Create approval token (HMAC) so frontend can build secure approve/reject URLs
        secret = (settings.SECRET_KEY or 'secret').encode('utf-8')
        msg = f"{topup.id}:{user.id}".encode('utf-8')
        approve_token = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        return Response({
            'transaction_id': topup.id,
            'status': 'pending',
            'amount': str(amount),
            'cashback': str(cashback),
            'promo_bonus': str(promo_bonus),
            'approve_token': approve_token,
        })


class ApproveTopupView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        txid = request.query_params.get('tx')
        token = request.query_params.get('token', '')
        if not txid or not token:
            return Response({'ok': False, 'error': 'missing params'}, status=400)
        try:
            tx = TopUpTransaction.objects.select_related('user').get(id=int(txid))
        except (TopUpTransaction.DoesNotExist, ValueError):
            return Response({'ok': False, 'error': 'tx not found'}, status=404)
        # validate HMAC
        secret = (settings.SECRET_KEY or 'secret').encode('utf-8')
        msg = f"{tx.id}:{tx.user_id}".encode('utf-8')
        expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, token):
            return Response({'ok': False, 'error': 'invalid token'}, status=403)
        _approve_topup_transaction(tx)
        # Try to remove inline buttons if we have cached message info
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        api_url = f"https://api.telegram.org/bot{bot_token}" if bot_token else None
        cache_key = f"topup_msg_{tx.id}"
        info = cache.get(cache_key)
        if api_url and info:
            chat_id = info.get('chat_id')
            message_id = info.get('message_id')
            if chat_id and message_id:
                try:
                    requests.post(
                        f"{api_url}/editMessageReplyMarkup",
                        data={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "reply_markup": json.dumps({"inline_keyboard": []}),
                        },
                        timeout=10,
                    )
                except Exception:
                    pass
        return Response({'ok': True, 'status': 'approved'})


class RejectTopupView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        txid = request.query_params.get('tx')
        token = request.query_params.get('token', '')
        if not txid or not token:
            return Response({'ok': False, 'error': 'missing params'}, status=400)
        try:
            tx = TopUpTransaction.objects.select_related('user').get(id=int(txid))
        except (TopUpTransaction.DoesNotExist, ValueError):
            return Response({'ok': False, 'error': 'tx not found'}, status=404)
        # validate HMAC
        secret = (settings.SECRET_KEY or 'secret').encode('utf-8')
        msg = f"{tx.id}:{tx.user_id}".encode('utf-8')
        expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, token):
            return Response({'ok': False, 'error': 'invalid token'}, status=403)
        # No state change, but remove inline buttons if possible
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        api_url = f"https://api.telegram.org/bot{bot_token}" if bot_token else None
        cache_key = f"topup_msg_{tx.id}"
        info = cache.get(cache_key)
        if api_url and info:
            chat_id = info.get('chat_id')
            message_id = info.get('message_id')
            if chat_id and message_id:
                try:
                    requests.post(
                        f"{api_url}/editMessageReplyMarkup",
                        data={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "reply_markup": json.dumps({"inline_keyboard": []}),
                        },
                        timeout=10,
                    )
                except Exception:
                    pass
        return Response({'ok': True, 'status': 'rejected'})


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = (JSONParser,)

    def post(self, request):
        payload = request.data or {}
        callback = payload.get('callback_query')
        if not callback:
            return Response({'ok': True})
        data = callback.get('data') or ''
        if ':' not in data:
            return Response({'ok': True})
        action, txid = data.split(':', 1)
        try:
            tx = TopUpTransaction.objects.select_related('user').get(id=int(txid))
        except (TopUpTransaction.DoesNotExist, ValueError):
            return Response({'ok': False, 'error': 'tx not found'})
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        chat_id = callback.get('message', {}).get('chat', {}).get('id')
        api_url = f"https://api.telegram.org/bot{token}" if token else None
        if action == 'approve':
            changed = _approve_topup_transaction(tx)
            # Remove inline buttons so others can't press again
            try:
                message_id = callback.get('message', {}).get('message_id')
                if api_url and chat_id and message_id:
                    requests.post(
                        f"{api_url}/editMessageReplyMarkup",
                        data={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "reply_markup": json.dumps({"inline_keyboard": []}),
                        },
                        timeout=10,
                    )
            except Exception:
                pass
            if api_url and chat_id:
                text = f"✅ Tasdiqlandi: Top-up #{tx.id} foydalanuvchi {tx.user.phone_number} uchun faollashtirildi."
                try:
                    requests.post(f"{api_url}/sendMessage", data={"chat_id": chat_id, "text": text}, timeout=10)
                except Exception:
                    pass
            return Response({'ok': True, 'status': 'approved'})
        elif action == 'reject':
            # Remove inline buttons on reject as well
            try:
                message_id = callback.get('message', {}).get('message_id')
                if api_url and chat_id and message_id:
                    requests.post(
                        f"{api_url}/editMessageReplyMarkup",
                        data={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "reply_markup": json.dumps({"inline_keyboard": []}),
                        },
                        timeout=10,
                    )
            except Exception:
                pass
            if api_url and chat_id:
                text = f"❌ Rad etildi: Top-up #{tx.id}"
                try:
                    requests.post(f"{api_url}/sendMessage", data={"chat_id": chat_id, "text": text}, timeout=10)
                except Exception:
                    pass
            return Response({'ok': True, 'status': 'rejected'})
        return Response({'ok': True})


class RegisterTopupTelegramMessageView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            tx = int(request.data.get('tx'))
            chat_id = request.data.get('chat_id')
            message_id = int(request.data.get('message_id'))
        except Exception:
            return Response({'ok': False, 'error': 'invalid payload'}, status=400)
        if not (tx and chat_id and message_id):
            return Response({'ok': False, 'error': 'missing fields'}, status=400)
        cache_key = f"topup_msg_{tx}"
        cache.set(cache_key, { 'chat_id': chat_id, 'message_id': message_id }, timeout=7*24*3600)
        return Response({ 'ok': True })

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-timestamp')

    @action(detail=False, methods=['post'], url_path='mark-read')
    def mark_read(self, request):
        Notification.objects.filter(user=request.user, read=False).update(read=True)
        return Response({'status': 'ok'})


class PartnerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PartnerSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Partner.objects.all().order_by('-created_at')


class AnnouncementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Announcement.objects.filter(is_active=True).order_by('-created_at')
        return qs
