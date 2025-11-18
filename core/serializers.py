from django.contrib.auth import authenticate
from decimal import Decimal
import secrets
from rest_framework import serializers
from django.conf import settings
import os
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, IdeaConfiguration, Project, ListedProject, Notification, TopUpTransaction, Partner, Promocode, PromocodeUsage, Announcement


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    referral_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['id', 'phone_number', 'password', 'full_name', 'workplace', 'referral_code']

    def create(self, validated_data):
        input_ref = validated_data.pop('referral_code', '').strip()
        password = validated_data.pop('password')
        # create user first
        user = User.objects.create_user(password=password, **validated_data)
        # generate unique referral_code for user
        if not user.referral_code:
            while True:
                code = secrets.token_hex(4).upper()  # 8 hex chars
                if not User.objects.filter(referral_code=code).exists():
                    user.referral_code = code
                    user.save(update_fields=['referral_code'])
                    break
        # apply referral bonus if valid
        if input_ref:
            referrer = User.objects.filter(referral_code__iexact=input_ref).first()
            if referrer and referrer != user:
                user.referred_by = referrer
                user.save(update_fields=['referred_by'])
                # credit 1000 so'm to referrer
                referrer.balance = (Decimal(referrer.balance) + Decimal('1000')).quantize(Decimal('0.01'))
                referrer.save(update_fields=['balance'])
                Notification.objects.create(
                    user=referrer,
                    type='success',
                    title='Referal bonusi',
                    message="Do'stingiz ro'yxatdan o'tdi. +1000 so'm qo'shildi."
                )
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
    referrals_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'phone_number', 'full_name', 'workplace', 'balance', 'is_subscribed', 'is_investor', 'date_joined', 'referral_code', 'referrals_count']

    def get_referrals_count(self, obj):
        return obj.referrals.count()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)


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
    receipt = serializers.FileField(required=False, allow_empty_file=False)

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
        if obj.logo and hasattr(obj.logo, 'name'):
            file_path = os.path.join(settings.MEDIA_ROOT, obj.logo.name)
            if os.path.exists(file_path):
                url = obj.logo.url
                if req:
                    return req.build_absolute_uri(url)
                return url
        return None


class AnnouncementSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = ['id', 'title', 'body', 'image_url', 'rules_url', 'submission_link', 'deadline', 'tags', 'is_active', 'created_at']
        read_only_fields = ['created_at', 'is_active']

    def get_image_url(self, obj):
        req = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            if req:
                return req.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
