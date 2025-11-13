from decimal import Decimal
from django.db import transaction
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User, IdeaConfiguration, Project, ListedProject, Notification, TopUpTransaction
from .serializers import (
    RegisterSerializer, PhoneTokenObtainPairSerializer, UserSerializer,
    IdeaConfigurationSerializer, ProjectSerializer, ListedProjectSerializer,
    NotificationSerializer, TopUpSerializer
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
            qs = ListedProject.objects.select_related('project', 'project__owner').all().order_by('-created_at')
        else:
            qs = self.get_queryset().order_by('-created_at')
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = ListedProjectSerializer(page, many=True)
            return self.get_paginated_response(ser.data)
        ser = ListedProjectSerializer(qs, many=True)
        return Response(ser.data)


class WalletView(generics.GenericAPIView):
    serializer_class = TopUpSerializer

    def post(self, request):
        """Create a pending top-up transaction. Admin approval will credit balance with 1% cashback."""
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        amount = ser.validated_data['amount']
        user = request.user
        cashback = (amount * Decimal('0.01')).quantize(Decimal('0.01'))
        with transaction.atomic():
            topup = TopUpTransaction.objects.create(user=user, amount=amount, cashback=cashback, is_active=False)
            Notification.objects.create(
                user=user,
                type='info',
                title='Top-up requested',
                message=f'{amount} so\'m to\'ldirish so\'rovi yuborildi. Admin tasdiqlagach balansingizga +{amount} va +{cashback} cashback qo\'shiladi.'
            )
        return Response({'transaction_id': topup.id, 'status': 'pending', 'amount': str(amount), 'cashback': str(cashback)})


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-timestamp')

    @action(detail=False, methods=['post'], url_path='mark-read')
    def mark_read(self, request):
        Notification.objects.filter(user=request.user, read=False).update(read=True)
        return Response({'status': 'ok'})
