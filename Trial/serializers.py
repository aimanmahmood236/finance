from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password, check_password
from .models import *
from datetime import datetime

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'full_name', 'password', 'monthly_income', 
                 'currency', 'profile_image', 'pin_hash', 'last_login']
        read_only_fields = ['id', 'last_login']
    
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user
    
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'icon', 'type', 'is_default', 'user', 'created_at']
        read_only_fields = ['id', 'created_at']

class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_icon = serializers.CharField(source='category.icon', read_only=True)
    
    class Meta:
        model = Transaction
        fields = ['id', 'user', 'category', 'category_name', 'category_icon', 'type', 
                 'amount', 'description', 'date', 'payment_method', 'receipt_image',
                 'is_recurring', 'recurring_id', 'created_at']
        read_only_fields = ['id', 'created_at']

class BudgetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    usage_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = Budget
        fields = ['id', 'user', 'category', 'category_name', 'month', 'year', 
                 'amount', 'spent', 'notification_threshold', 'usage_percentage', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_usage_percentage(self, obj):
        if obj.amount > 0:
            return float((obj.spent / obj.amount) * 100)
        return 0

class GoalSerializer(serializers.ModelSerializer):
    progress_percentage = serializers.ReadOnlyField()
    days_remaining = serializers.ReadOnlyField()
    monthly_needed = serializers.ReadOnlyField()
    
    class Meta:
        model = Goal
        fields = ['id', 'user', 'name', 'target_amount', 'current_amount', 
                 'target_date', 'icon', 'notes', 'created_at', 'progress_percentage',
                 'days_remaining', 'monthly_needed']
        read_only_fields = ['id', 'created_at', 'current_amount']

class GoalContributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoalContribution
        fields = ['id', 'goal', 'amount', 'date', 'transaction']

class BillSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    next_due_date = serializers.SerializerMethodField()
    
    class Meta:
        model = Bill
        fields = ['id', 'user', 'name', 'amount', 'category', 'category_name', 
                 'due_day', 'due_month', 'recurrence', 'reminder_days_before', 
                 'is_active', 'next_due_date', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_next_due_date(self, obj):
        today = datetime.now().date()
        current_year = today.year
        current_month = today.month
        
        if obj.recurrence == 'monthly':
            # Calculate next monthly due date
            due_date = datetime(current_year, current_month, obj.due_day).date()
            if due_date < today:
                if current_month == 12:
                    due_date = datetime(current_year + 1, 1, obj.due_day).date()
                else:
                    due_date = datetime(current_year, current_month + 1, obj.due_day).date()
            return due_date
        elif obj.recurrence == 'yearly' and obj.due_month:
            due_date = datetime(current_year, obj.due_month, obj.due_day).date()
            if due_date < today:
                due_date = datetime(current_year + 1, obj.due_month, obj.due_day).date()
            return due_date
        return None

class BillPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillPayment
        fields = ['id', 'bill', 'amount_paid', 'paid_date', 'transaction']

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'user', 'type', 'title', 'message', 'data', 'is_read', 'created_at']
        read_only_fields = ['id', 'created_at']

class AppSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppSetting
        fields = '__all__'