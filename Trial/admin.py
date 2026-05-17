from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Category, Transaction, Budget, Goal, Bill, Notification, AppSetting

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'full_name', 'email', 'monthly_income', 'currency', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('full_name', 'monthly_income', 'currency', 'profile_image', 'pin_hash')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Additional Info', {'fields': ('full_name', 'email', 'monthly_income', 'currency')}),
    )

admin.site.register(User, CustomUserAdmin)
admin.site.register(Category)
admin.site.register(Transaction)
admin.site.register(Budget)
admin.site.register(Goal)
admin.site.register(Bill)
admin.site.register(Notification)
admin.site.register(AppSetting)