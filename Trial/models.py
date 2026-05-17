from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import json

class User(AbstractUser):
    # Extend Django's built-in User model
    full_name = models.CharField(max_length=255)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="UGX")
    profile_image = models.CharField(max_length=500, blank=True, null=True)
    pin_hash = models.CharField(max_length=255, blank=True, null=True)
    last_login = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
    
    def __str__(self):
        return self.full_name or self.username

class Category(models.Model):
    TYPE_CHOICES = [('expense', 'Expense'),('income', 'Income'),]
    
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, blank=True, null=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    is_default = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='categories')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'categories'
        unique_together = ['name', 'user', 'type']  # Prevent duplicates
    
    def __str__(self):
        return f"{self.name} ({self.type})"

class Transaction(models.Model):
    TYPE_CHOICES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]
    
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
        ('other', 'Other'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='transactions')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True, null=True)
    receipt_image = models.CharField(max_length=500, blank=True, null=True)
    is_recurring = models.BooleanField(default=False)
    recurring_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'transactions'
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.type}: {self.amount} on {self.date}"

class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budgets')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='budgets')
    month = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    year = models.IntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notification_threshold = models.IntegerField(default=80, validators=[MinValueValidator(0), MaxValueValidator(100)])
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'budgets'
        unique_together = ['user', 'category', 'month', 'year']
    
    def __str__(self):
        return f"{self.category.name} - {self.month}/{self.year}: {self.amount}"
    
    @property
    def usage_percentage(self):
        """Calculate usage percentage"""
        if self.amount > 0:
            return float((self.spent / self.amount) * 100)
        return 0

    def usage_percentage(self):
        """Calculate usage percentage"""
        if self.amount > 0:
           return float((self.spent / self.amount) * 100)
        return 0

class Goal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='goals')
    name = models.CharField(max_length=200)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    target_date = models.DateField()
    icon = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'goals'
    
    @property
    def progress_percentage(self):
        if self.target_amount > 0:
            return float((self.current_amount / self.target_amount) * 100)
        return 0
    
    @property
    def days_remaining(self):
        return (self.target_date - timezone.now().date()).days
    
    @property
    def monthly_needed(self):
        days_left = max(1, self.days_remaining)
        months_left = max(1, days_left / 30)
        remaining = self.target_amount - self.current_amount
        if remaining > 0:
            return float(remaining / months_left)
        return 0
    
    def __str__(self):
        return self.name

class GoalContribution(models.Model):
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name='contributions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(auto_now_add=True)
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='goal_contributions')
    
    class Meta:
        db_table = 'goal_contributions'
    
    def __str__(self):
        return f"Contribution to {self.goal.name}: {self.amount}"

class Bill(models.Model):
    RECURRENCE_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('one-time', 'One Time'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bills')
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='bills')
    due_day = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(31)])
    due_month = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], null=True, blank=True)
    recurrence = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, default='monthly')
    reminder_days_before = models.IntegerField(default=3)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'bills'
    
    def __str__(self):
        return self.name

class BillPayment(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='payments')
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    paid_date = models.DateField(auto_now_add=True)
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='bill_payments')
    
    class Meta:
        db_table = 'bill_payments'
    
    def __str__(self):
        return f"Payment for {self.bill.name}: {self.amount_paid}"

class Notification(models.Model):
    TYPE_CHOICES = [
        ('budget_alert', 'Budget Alert'),
        ('bill_reminder', 'Bill Reminder'),
        ('goal_milestone', 'Goal Milestone'),
        ('weekly_report', 'Weekly Report'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    data = models.JSONField(default=dict)  # Stores JSON for navigation
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title

class AppSetting(models.Model):
    THEME_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('system', 'System'),
    ]
    
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('sw', 'Swahili'),
        ('lg', 'Luganda'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='settings')
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='light')
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='en')
    currency = models.CharField(max_length=3, default='UGX')
    notifications_enabled = models.BooleanField(default=True)
    budget_alerts = models.BooleanField(default=True)
    bill_reminders = models.BooleanField(default=True)
    goal_milestones = models.BooleanField(default=True)
    weekly_summary = models.BooleanField(default=True)
    auto_lock_minutes = models.IntegerField(default=5)
    biometric_login = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'app_settings'
    
    def __str__(self):
        return f"Settings for {self.user.username}"