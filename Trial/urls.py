from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'categories', views.CategoryViewSet)
router.register(r'transactions', views.TransactionViewSet)
router.register(r'budgets', views.BudgetViewSet)
router.register(r'goals', views.GoalViewSet)
router.register(r'bills', views.BillViewSet)
router.register(r'notifications', views.NotificationViewSet)
router.register(r'settings', views.AppSettingViewSet)

urlpatterns = [
    # API endpoints
    path('', include(router.urls)),
    path('auth/token/', obtain_auth_token, name='api_token_auth'),
    
    # HTML form pages
    path('add-users/', views.add_users_page, name='add_users_page'),
    path('add-categories/', views.add_categories_page, name='add_categories_page'),
    path('transactions-page/', views.transactions_page, name='transactions_page'),
    path('transactions/delete/<int:id>/', views.transactions_page, name='delete_transaction'),
    path('budgets-page/', views.budgets_page, name='budgets_page'),
    path('budgets/delete/<int:id>/', views.budgets_page, name='delete_budget'),
    path('goals-page/', views.goals_page, name='goals_page'),
    path('goals/delete/<int:id>/', views.goals_page, name='delete_goal'),
    path('goals/contribute/', views.goals_page, name='contribute_goal'),
    path('contributions-page/', views.contributions_page, name='contributions_page'),
    path('contributions/delete/<int:id>/', views.contributions_page, name='delete_contribution'),
    path('bills-page/', views.bills_page, name='bills_page'),
    path('bills/delete/<int:id>/', views.bills_page, name='delete_bill'),
    path('bills/mark-paid/<int:id>/', views.bills_page, name='mark_paid'),
    path('bills/toggle/<int:id>/', views.bills_page, name='toggle_bill'),
    path('bill-payments-page/', views.bill_payments_page, name='bill_payments_page'),
    path('bill-payments/delete/<int:id>/', views.bill_payments_page, name='delete_bill_payment'),
    path('notifications-page/', views.notifications_page, name='notifications_page'),
    path('notifications/mark-read/<int:id>/', views.notifications_page, name='mark_read'),
    path('notifications/mark-unread/<int:id>/', views.notifications_page, name='mark_unread'),
    path('notifications/mark-all-read/', views.notifications_page, name='mark_all_read'),
    path('notifications/delete/<int:id>/', views.notifications_page, name='delete_notification'),
    path('settings-page/', views.settings_page, name='settings_page'),
    path('settings/reset/', views.reset_settings, name='reset_settings'),
    path('dashboard/', views.dashboard_page, name='dashboard'),
    path('test/', views.test_page, name='test_page'),
    path('', views.dashboard_page, name='home'),  # Make dashboard the home page
]  # ← Closing bracket here - this is correct