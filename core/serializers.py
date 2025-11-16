from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, IdeaConfiguration, Project, ListedProject, Notification, TopUpTransaction, Partner, Promocode, PromocodeUsage


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'phone_number', 'password', 'full_name', 'workplace']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(password=password, **validated_data)
        return user


class PhoneTokenObtainPairSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        phone = attrs.get('phone_number')
        password = attrs.get('password')
        if not phone or not password:
            raise serializers.ValidationError('phone_number and password are required')
        user = authenticate(request=self.context.get('request'), username=phone, password=password)
        if not user:
            raise serializers.ValidationError('Invalid credentials')
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'phone_number', 'full_name', 'workplace', 'balance', 'is_subscribed', 'date_joined']


class IdeaConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = IdeaConfiguration
        fields = '__all__'
        read_only_fields = ['owner', 'created_at']


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ['owner', 'created_at']


class ListedProjectSerializer(serializers.ModelSerializer):
    projectName = serializers.CharField(source='project.project_name', read_only=True)
    description = serializers.CharField(source='project.description', read_only=True)
    founderPhone = serializers.CharField(source='project.owner.phone_number', read_only=True)
    founderName = serializers.CharField(source='project.owner.full_name', read_only=True)
    projectId = serializers.IntegerField(source='project.id', read_only=True)
    project_data = serializers.JSONField(source='project.data', read_only=True)

    class Meta:
        model = ListedProject
        fields = ['id', 'project', 'projectId', 'projectName', 'description', 'funding_sought', 'equity_offered', 'pitch', 'founderPhone', 'founderName', 'project_data', 'created_at']
        read_only_fields = ['created_at', 'projectId', 'projectName', 'description', 'founderPhone', 'founderName', 'project_data']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['timestamp', 'user']


class TopUpSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    promo_code = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        amount = attrs.get('amount')
        if amount is None or amount <= 0:
            raise serializers.ValidationError({'amount': 'Amount must be positive'})

        code = attrs.get('promo_code', '').strip()
        if code:
            try:
                promo = Promocode.objects.get(code__iexact=code, is_active=True)
            except Promocode.DoesNotExist:
                raise serializers.ValidationError({'promo_code': 'Invalid or inactive promo code'})

            user = self.context.get('request').user
            if PromocodeUsage.objects.filter(user=user, promocode=promo).exists():
                raise serializers.ValidationError({'promo_code': 'Promo code already used by this user'})

            attrs['promo'] = promo
        return attrs


class PartnerSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Partner
        fields = ['id', 'name', 'short_info', 'contact_person', 'contact_phone', 'website', 'logo_url', 'created_at']
        read_only_fields = ['created_at']

    def get_logo_url(self, obj):
        req = self.context.get('request')
        if obj.logo and hasattr(obj.logo, 'url'):
            if req:
                return req.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None
