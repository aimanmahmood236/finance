from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.db.models import Sum, Q,Avg
from django.utils import timezone

from datetime import datetime, timedelta
from django.shortcuts import render
from django.http import HttpResponse
from .models import *
from .serializers import *
from django.db import models
from dateutil.relativedelta import relativedelta  # Add this import
from django.db import models  # Add this at the top with other imports
from django.contrib.auth.hashers import make_password
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import HttpResponse
from decimal import Decimal

@ensure_csrf_cookie
def add_users_page(request):
    """HTML page to add users"""
    message = ""
    message_type = ""
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        email = request.POST.get('email')
        full_name = request.POST.get('full_name')
        monthly_income = request.POST.get('monthly_income')
        currency = request.POST.get('currency', 'UGX')
        
        # Validate passwords match
        if password != confirm_password:
            message = "Passwords do not match!"
            message_type = "error"
        elif not username or not password:
            message = "Username and password are required!"
            message_type = "error"
        elif User.objects.filter(username=username).exists():
            message = f"User '{username}' already exists!"
            message_type = "error"
        else:
            # Create user
            user = User.objects.create(
                username=username,
                password=make_password(password),
                email=email,
                full_name=full_name,
                monthly_income=Decimal(monthly_income) if monthly_income else None,
                currency=currency
            )
            message = f"User '{username}' created successfully!"
            message_type = "success"
    
    # Instead of returning HTML string, use render with a template
    return render(request, 'add_users.html', {
        'message': message,
        'message_type': message_type
    })


# ============================================================================
# API VIEWSETS
# ============================================================================

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action in ['register', 'login_user']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        if self.request.user.is_authenticated:
            return User.objects.filter(id=self.request.user.id)
        return User.objects.none()
    
    @action(detail=False, methods=['post'])
    def register(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Create default categories
            default_expense_categories = [
                ('Food & Dining', '🍔'), ('Transport', '🚗'), ('Housing', '🏠'),
                ('Utilities', '💡'), ('Entertainment', '🎬'), ('Shopping', '🛍️'),
                ('Healthcare', '🏥'), ('Education', '📚'), ('Personal Care', '💇'),
                ('Gifts', '🎁'), ('Other', '📌')
            ]
            
            default_income_categories = [
                ('Salary', '💰'), ('Freelance', '💻'), ('Business', '🏢'),
                ('Gift', '🎁'), ('Investment', '📈'), ('Other', '📌')
            ]
            
            for name, icon in default_expense_categories:
                Category.objects.create(
                    name=name, icon=icon, type='expense', 
                    is_default=True, user=user
                )
            
            for name, icon in default_income_categories:
                Category.objects.create(
                    name=name, icon=icon, type='income', 
                    is_default=True, user=user
                )
            
            # Create app settings
            AppSetting.objects.create(user=user)
            
            return Response({
                'message': 'User registered successfully',
                'user': serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def login_user(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        user = authenticate(username=username, password=password)
        if user:
            token, created = Token.objects.get_or_create(user=user)
            user.last_login = timezone.now()
            user.save()
            
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data,
                'message': 'Login successful'
            })
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        user = request.user
        today = timezone.now().date()
        
        current_month = today.month
        current_year = today.year
        
        monthly_transactions = Transaction.objects.filter(
            user=user,
            date__year=current_year,
            date__month=current_month
        )
        
        total_income = monthly_transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
        total_expense = monthly_transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
        
        recent_transactions = monthly_transactions.order_by('-date')[:10]
        
        category_spending = monthly_transactions.filter(type='expense').values(
            'category__name', 'category__icon'
        ).annotate(total=Sum('amount')).order_by('-total')[:5]
        
        return Response({
            'balance': total_income - total_expense,
            'total_income': total_income,
            'total_expense': total_expense,
            'recent_transactions': TransactionSerializer(recent_transactions, many=True).data,
            'top_categories': category_spending
        })


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Category.objects.filter(
            Q(user=self.request.user) | Q(is_default=True, user__isnull=True)
        ).distinct()
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['description', 'category__name']
    ordering_fields = ['date', 'amount']
    
    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        trans_type = self.request.query_params.get('type')
        category = self.request.query_params.get('category')
        
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        if trans_type:
            queryset = queryset.filter(type=trans_type)
        if category:
            queryset = queryset.filter(category_id=category)
        
        return queryset
    
    def perform_create(self, serializer):
        transaction = serializer.save(user=self.request.user)
        
        if transaction.type == 'expense' and transaction.category:
            budget = Budget.objects.filter(
                user=self.request.user,
                category=transaction.category,
                month=transaction.date.month,
                year=transaction.date.year
            ).first()
            
            if budget:
                budget.spent += transaction.amount
                budget.save()
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        today = timezone.now().date()
        start_of_month = today.replace(day=1)
        
        transactions = Transaction.objects.filter(
            user=request.user,
            date__gte=start_of_month,
            date__lte=today
        )
        
        total_income = transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
        total_expense = transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
        
        return Response({
            'total_income': total_income,
            'total_expense': total_expense,
            'net_savings': total_income - total_expense,
            'transaction_count': transactions.count()
        })


class BudgetViewSet(viewsets.ModelViewSet):
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Budget.objects.filter(user=self.request.user)
        
        month = self.request.query_params.get('month')
        year = self.request.query_params.get('year')
        
        if month:
            queryset = queryset.filter(month=month)
        if year:
            queryset = queryset.filter(year=year)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def check_alerts(self, request):
        current_month = timezone.now().month
        current_year = timezone.now().year
        
        budgets = Budget.objects.filter(
            user=request.user,
            month=current_month,
            year=current_year
        )
        
        alerts = []
        for budget in budgets:
            usage = (budget.spent / budget.amount * 100) if budget.amount > 0 else 0
            if usage >= budget.notification_threshold:
                alerts.append({
                    'category': budget.category.name,
                    'budget_amount': budget.amount,
                    'spent': budget.spent,
                    'percentage': usage,
                    'remaining': budget.amount - budget.spent
                })
        
        return Response({'alerts': alerts})


class GoalViewSet(viewsets.ModelViewSet):
    queryset = Goal.objects.all()
    serializer_class = GoalSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Goal.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def add_money(self, request, pk=None):
        goal = self.get_object()
        amount = float(request.data.get('amount', 0))
        
        if amount <= 0:
            return Response({'error': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)
        
        goal.current_amount += amount
        goal.save()
        
        GoalContribution.objects.create(
            goal=goal,
            amount=amount,
            date=timezone.now().date()
        )
        
        if goal.current_amount >= goal.target_amount:
            Notification.objects.create(
                user=request.user,
                type='goal_milestone',
                title='Goal Achieved! 🎉',
                message=f'Congratulations! You have achieved your goal: {goal.name}',
                data={'goal_id': goal.id}
            )
        
        return Response({
            'message': f'Added {amount} to {goal.name}',
            'current_amount': goal.current_amount,
            'progress': goal.progress_percentage
        })


class BillViewSet(viewsets.ModelViewSet):
    queryset = Bill.objects.all()
    serializer_class = BillSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Bill.objects.filter(user=self.request.user, is_active=True)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        bill = self.get_object()
        amount = float(request.data.get('amount', bill.amount))
        
        transaction = Transaction.objects.create(
            user=request.user,
            category=bill.category,
            type='expense',
            amount=amount,
            description=f"Bill payment: {bill.name}",
            date=timezone.now().date(),
            is_recurring=False
        )
        
        BillPayment.objects.create(
            bill=bill,
            amount_paid=amount,
            transaction=transaction
        )
        
        if bill.recurrence == 'one_time':
            bill.is_active = False
            bill.save()
        
        return Response({
            'message': f'Bill {bill.name} marked as paid',
            'transaction_id': transaction.id
        })


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'All notifications marked as read'})
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'unread_count': count})


class AppSettingViewSet(viewsets.ModelViewSet):
    queryset = AppSetting.objects.all()
    serializer_class = AppSettingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return AppSetting.objects.filter(user=self.request.user)
    
    def retrieve(self, request, *args, **kwargs):
        settings, created = AppSetting.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(settings)
        return Response(serializer.data)
    
    
    
    def update(self, request, *args, **kwargs):
        settings, created = AppSetting.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    def test_page(request):
        return render(request, 'test.html', {'test_variable': 'Hello World!'})
    


# ============================================================================
# HTML VIEWS - For web interface
# ============================================================================

def add_users_page(request):
    """HTML page to add users"""
    from django.contrib.auth.hashers import make_password
    from decimal import Decimal
    
    message = ""
    message_type = ""
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        email = request.POST.get('email')
        full_name = request.POST.get('full_name')
        monthly_income = request.POST.get('monthly_income')
        currency = request.POST.get('currency', 'UGX')
        
        # Validate passwords match
        if password != confirm_password:
            message = "Passwords do not match!"
            message_type = "error"
        elif not username or not password:
            message = "Username and password are required!"
            message_type = "error"
        elif User.objects.filter(username=username).exists():
            message = f"User '{username}' already exists!"
            message_type = "error"
        else:
            # Create user
            user = User.objects.create(
                username=username,
                password=make_password(password),
                email=email,
                full_name=full_name,
                monthly_income=Decimal(monthly_income) if monthly_income else None,
                currency=currency
            )
            message = f"User '{username}' created successfully!"
            message_type = "success"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Add User</title>
        <style>
            body {{ font-family: Arial; padding: 20px; max-width: 600px; margin: auto; }}
            input, select, button {{ margin: 10px 0; padding: 8px; width: 100%; }}
            button {{ background: #007bff; color: white; border: none; cursor: pointer; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
            .nav a {{ margin: 0 10px; }}
            .form-group {{ margin-bottom: 15px; }}
            label {{ font-weight: bold; display: block; margin-bottom: 5px; }}
        </style>
    </head>
    <body>
        <div class="nav">
            <a href="/api/add-users/">Add User</a>
            <a href="/api/add-categories/">Add Category</a>
            <a href="/api/transactions-page/">Transactions</a>
            <a href="/admin/">Admin</a>
        </div>
        <h2>Add New User</h2>
        
        {f'<div class="{message_type}">{message}</div>' if message else ''}
        
        <form method="POST">
            <div class="form-group">
                <label>Username *</label>
                <input type="text" name="username" required>
            </div>
            
            <div class="form-group">
                <label>Full Name</label>
                <input type="text" name="full_name">
            </div>
            
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email">
            </div>
            
            <div class="form-group">
                <label>Password *</label>
                <input type="password" name="password" required>
            </div>
            
            <div class="form-group">
                <label>Confirm Password *</label>
                <input type="password" name="confirm_password" required>
            </div>
            
            <div class="form-group">
                <label>Monthly Income (UGX)</label>
                <input type="number" name="monthly_income" step="0.01" placeholder="0.00">
            </div>
            
            <div class="form-group">
                <label>Currency</label>
                <select name="currency">
                    <option value="UGX">UGX - Ugandan Shilling</option>
                    <option value="USD">USD - US Dollar</option>
                    <option value="EUR">EUR - Euro</option>
                    <option value="GBP">GBP - British Pound</option>
                </select>
            </div>
            
            <button type="submit">Create User</button>
        </form>
    </body>
    </html>
    """
    
    from django.http import HttpResponse
    return HttpResponse(html)

def add_categories_page(request):
    """HTML page to add categories"""
    message = ""
    message_type = ""
    
    # Handle form submission
    if request.method == 'POST':
        name = request.POST.get('name')
        icon = request.POST.get('icon')
        category_type = request.POST.get('type')
        
        if name and category_type:
            category = Category.objects.create(
                name=name,
                icon=icon or '📌',
                type=category_type,
                is_default=False,
                user=request.user if request.user.is_authenticated else None
            )
            message = f"Category '{name}' created successfully!"
            message_type = "success"
        else:
            message = "Name and type are required!"
            message_type = "error"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Add Category</title>
        <style>
            body {{ font-family: Arial; padding: 20px; max-width: 500px; margin: auto; }}
            input, select, button {{ margin: 10px 0; padding: 8px; width: 100%; }}
            button {{ background: #28a745; color: white; border: none; cursor: pointer; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
            .nav a {{ margin: 0 10px; }}
        </style>
    </head>
    <body>
        <div class="nav">
            <a href="/api/add-users/">Add User</a>
            <a href="/api/add-categories/">Add Category</a>
            <a href="/admin/">Admin</a>
        </div>
        <h2>Add New Category</h2>
        {f'<div class="{message_type}">{message}</div>' if message else ''}
        <form method="POST">
            <input type="text" name="name" placeholder="Category Name" required>
            <input type="text" name="icon" placeholder="Icon (emoji)" value="📌">
            <select name="type" required>
                <option value="expense">Expense</option>
                <option value="income">Income</option>
            </select>
            <button type="submit">Create Category</button>
        </form>
    </body>
    </html>
    """
    return HttpResponse(html)

def transactions_page(request):
    """HTML page to manage transactions"""
    from django.http import HttpResponse
    from django.shortcuts import render, redirect
    from django.contrib.auth.hashers import make_password
    from decimal import Decimal
    from datetime import date
    
    message = ""
    message_type = ""
    
    # Handle POST request (Add transaction)
    if request.method == 'POST':
        try:
            transaction_type = request.POST.get('type')
            category_id = request.POST.get('category_id')
            amount = request.POST.get('amount')
            date_str = request.POST.get('date')
            payment_method = request.POST.get('payment_method')
            description = request.POST.get('description')
            
            if transaction_type and category_id and amount and date_str:
                category = Category.objects.get(id=category_id)
                
                transaction = Transaction.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    category=category,
                    type=transaction_type,
                    amount=Decimal(amount),
                    date=date_str,
                    payment_method=payment_method,
                    description=description
                )
                message = f"Transaction of {amount} added successfully!"
                message_type = "success"
            else:
                message = "Please fill all required fields!"
                message_type = "error"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    # Handle DELETE request
    if request.method == 'GET' and 'delete' in request.path:
        transaction_id = request.path.split('/')[-2]
        try:
            transaction = Transaction.objects.get(id=transaction_id)
            transaction.delete()
            message = "Transaction deleted successfully!"
            message_type = "success"
        except:
            message = "Transaction not found!"
            message_type = "error"
    
    # Get filter parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    type_filter = request.GET.get('type_filter')
    category_filter = request.GET.get('category_filter')
    
    # Get transactions
    transactions = Transaction.objects.all()
    if request.user.is_authenticated:
        transactions = transactions.filter(user=request.user)
    
    # Apply filters
    if start_date:
        transactions = transactions.filter(date__gte=start_date)
    if end_date:
        transactions = transactions.filter(date__lte=end_date)
    if type_filter:
        transactions = transactions.filter(type=type_filter)
    if category_filter:
        transactions = transactions.filter(category_id=category_filter)
    
    # Calculate totals
    total_income = transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
    total_expense = transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
    balance = total_income - total_expense
    
    # Get all categories for dropdown
    categories = Category.objects.all()
    if request.user.is_authenticated:
        categories = categories.filter(Q(user=request.user) | Q(is_default=True))

    unread_count =0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    context = {
        'transactions': transactions.order_by('-date'),
        'categories': categories,
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
        'message': message,
        'message_type': message_type,
        'today': date.today().isoformat(),
        'start_date': start_date,
        'end_date': end_date,
        'type_filter': type_filter,
        'category_filter': category_filter,
        'active_page': 'page_name',
        'unread_count': unread_count,
    }
        
    return render(request, 'transactions.html', context)

def budgets_page(request):
    """HTML page to manage budgets"""
    from django.shortcuts import render, redirect
    from django.http import HttpResponse
    from datetime import datetime
    from decimal import Decimal
    
    message = ""
    message_type = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Handle POST request (Add/Update budget)
    if request.method == 'POST':
        try:
            category_id = request.POST.get('category_id')
            month = int(request.POST.get('month'))
            year = int(request.POST.get('year'))
            amount = Decimal(request.POST.get('amount'))
            notification_threshold = int(request.POST.get('notification_threshold', 80))
            
            if category_id and amount:
                category = Category.objects.get(id=category_id)
                
                # Check if budget already exists
                budget, created = Budget.objects.get_or_create(
                    user=request.user if request.user.is_authenticated else None,
                    category=category,
                    month=month,
                    year=year,
                    defaults={
                        'amount': amount,
                        'notification_threshold': notification_threshold
                    }
                )
                
                if not created:
                    # Update existing budget
                    budget.amount = amount
                    budget.notification_threshold = notification_threshold
                    budget.save()
                    message = f"Budget for {category.name} updated successfully!"
                else:
                    message = f"Budget for {category.name} created successfully!"
                message_type = "success"
            else:
                message = "Please fill all required fields!"
                message_type = "error"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    # Handle DELETE request
    if request.method == 'GET' and 'delete' in request.path:
        budget_id = request.path.split('/')[-2]
        try:
            budget = Budget.objects.get(id=budget_id)
            category_name = budget.category.name
            budget.delete()
            message = f"Budget for {category_name} deleted successfully!"
            message_type = "success"
        except:
            message = "Budget not found!"
            message_type = "error"
    
    # Get filter parameters
    filter_month = request.GET.get('filter_month')
    filter_year = request.GET.get('filter_year')
    
    # Get budgets
    budgets = Budget.objects.all()
    if request.user.is_authenticated:
        budgets = budgets.filter(user=request.user)
    
    # Apply filters
    if filter_month:
        budgets = budgets.filter(month=int(filter_month))
    if filter_year:
        budgets = budgets.filter(year=int(filter_year))
    
    # Calculate spent amount for each budget
    for budget in budgets:
        spent = Transaction.objects.filter(
            user=request.user if request.user.is_authenticated else None,
            category=budget.category,
            type='expense',
            date__year=budget.year,
            date__month=budget.month
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        budget.spent = spent
        budget.remaining = budget.amount - spent
        budget.usage_percentage = (spent / budget.amount * 100) if budget.amount > 0 else 0
        budget.save()
    
    # Calculate totals
    total_budget = sum(b.amount for b in budgets)
    total_spent = sum(b.spent for b in budgets)
    total_remaining = total_budget - total_spent
    overall_percentage = (total_spent / total_budget * 100) if total_budget > 0 else 0
    
    # Check for alerts
    alerts = []
    for budget in budgets:
        if budget.usage_percentage >= budget.notification_threshold:
            alerts.append({
                'category': budget.category.name,
                'budget': budget.amount,
                'spent': budget.spent,
                'percentage': budget.usage_percentage,
                'threshold': budget.notification_threshold
            })
    
    # Get expense categories for dropdown
    expense_categories = Category.objects.filter(type='expense')
    if request.user.is_authenticated:
        expense_categories = expense_categories.filter(
            Q(user=request.user) | Q(is_default=True)
        ).distinct()
    
    # Month name mapping
    month_names = {
        1: 'January', 2: 'February', 3: 'March', 4: 'April',
        5: 'May', 6: 'June', 7: 'July', 8: 'August',
        9: 'September', 10: 'October', 11: 'November', 12: 'December'
    }

    unread_count =0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    
    context = {
        'budgets': budgets if budgets else [],
        'expense_categories': expense_categories if expense_categories else [],
        'total_budget': total_budget or 0,
        'total_spent': total_spent or 0,
        'total_remaining': total_remaining or 0,
        'overall_percentage': round(overall_percentage, 1) if overall_percentage else 0,
        'alerts': alerts or [],
        'message': message or '',
        'message_type': message_type or '',
        'year': current_year,
        'filter_month': filter_month or '',
        'filter_year': filter_year or '',
        'active_page': 'page_name',
        'unread_count': unread_count,
    }
    
    return render(request, 'budgets.html', context)


def goals_page(request):
    """HTML page to manage savings goals"""
    from django.shortcuts import render
    from django.db.models import Sum, F
    from datetime import date
    from decimal import Decimal
    from .models import Goal, GoalContribution, Notification  # Make sure Goal is imported
    
    message = ""
    message_type = ""
    today = date.today()
    
    # Get unread count
    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    # Handle POST request (Add goal or contribution)
    if request.method == 'POST':
        # Check if it's a contribution
        if 'goal_id' in request.POST:
            # Add contribution to goal
            goal_id = request.POST.get('goal_id')
            amount = Decimal(request.POST.get('amount', 0))
            contribution_date = request.POST.get('date', today)
            
            try:
                goal = Goal.objects.get(id=goal_id)
                if request.user.is_authenticated:
                    goal = Goal.objects.filter(id=goal_id, user=request.user).first()
                
                if goal:
                    goal.current_amount += amount
                    goal.save()
                    
                    # Create contribution record
                    GoalContribution.objects.create(
                        goal=goal,
                        amount=amount,
                        date=contribution_date
                    )
                    
                    message = f"Added UGX {amount:,.0f} to '{goal.name}'!"
                    message_type = "success"
                else:
                    message = "Goal not found!"
                    message_type = "error"
            except Exception as e:
                message = f"Error: {str(e)}"
                message_type = "error"
        else:
            # Create new goal
            name = request.POST.get('name')
            icon = request.POST.get('icon', '🎯')
            target_amount = Decimal(request.POST.get('target_amount', 0))
            current_amount = Decimal(request.POST.get('current_amount', 0))
            target_date = request.POST.get('target_date')
            notes = request.POST.get('notes', '')
            
            if name and target_amount and target_date:
                Goal.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    name=name,
                    icon=icon,
                    target_amount=target_amount,
                    current_amount=current_amount,
                    target_date=target_date,
                    notes=notes
                )
                message = f"Goal '{name}' created successfully!"
                message_type = "success"
            else:
                message = "Please fill all required fields!"
                message_type = "error"
    
    # Handle DELETE request
    if request.method == 'GET' and 'delete' in request.path:
        goal_id = request.path.split('/')[-2]
        try:
            goal = Goal.objects.get(id=goal_id)
            if request.user.is_authenticated:
                goal = Goal.objects.filter(id=goal_id, user=request.user).first()
            if goal:
                goal_name = goal.name
                goal.delete()
                message = f"Goal '{goal_name}' deleted successfully!"
                message_type = "success"
        except:
            message = "Goal not found!"
            message_type = "error"
    
    # Get all goals
    goals = Goal.objects.all()
    if request.user.is_authenticated:
        goals = goals.filter(user=request.user)
    
    # Calculate additional properties for each goal
    for goal in goals:
        goal.remaining = goal.target_amount - goal.current_amount
        goal.days_remaining = (goal.target_date - today).days
        if goal.days_remaining > 0:
            months_left = max(1, goal.days_remaining / 30)
            goal.monthly_needed = goal.remaining / months_left if goal.remaining > 0 else 0
        else:
            goal.monthly_needed = 0
        goal.progress_percentage = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
    
    # Calculate totals
    total_goals = goals.count()
    total_target = sum(g.target_amount for g in goals)
    total_saved = sum(g.current_amount for g in goals)
    overall_progress = (total_saved / total_target * 100) if total_target > 0 else 0
    
    context = {
        'goals': goals,
        'total_goals': total_goals,
        'total_target': total_target,
        'total_saved': total_saved,
        'overall_progress': round(overall_progress, 1),
        'message': message,
        'message_type': message_type,
        'today': today.isoformat(),
        'active_page': 'goals',
        'unread_count': unread_count,
        'currency': 'UGX',
    }
    
    return render(request, 'goals.html', context)
##def contributions_page(request):
    """HTML page to manage goal contributions"""
    from django.shortcuts import render
    from django.db.models import Sum, Avg, F
    from datetime import date
    from decimal import Decimal
    from .models import Goal, GoalContribution, Transaction, Notification
    
    message = ""
    message_type = ""
    today = date.today()
    
    # Get unread count
    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    # Handle POST request (Add contribution)
    if request.method == 'POST':
        goal_id = request.POST.get('goal_id')
        amount = Decimal(request.POST.get('amount', 0))
        contribution_date = request.POST.get('date', today)
        transaction_id = request.POST.get('transaction_id')
        
        if goal_id and amount > 0:
            try:
                goal = Goal.objects.get(id=goal_id)
                if request.user.is_authenticated:
                    goal = Goal.objects.filter(id=goal_id, user=request.user).first()
                
                if goal:
                    # Create contribution
                    contribution = GoalContribution.objects.create(
                        goal=goal,
                        amount=amount,
                        date=contribution_date,
                        transaction_id=transaction_id if transaction_id else None
                    )
                    
                    # Update goal current amount
                    goal.current_amount += amount
                    goal.save()
                    
                    # Check if goal is achieved
                    if goal.current_amount >= goal.target_amount:
                        Notification.objects.create(
                            user=request.user if request.user.is_authenticated else None,
                            type='goal_milestone',
                            title='Goal Achieved! 🎉',
                            message=f'Congratulations! You have achieved your goal: {goal.name}',
                            data={'goal_id': goal.id}
                        )
                        message = f"🎉 Congratulations! You've achieved your goal '{goal.name}'!"
                    else:
                        message = f"Added UGX {amount:,.0f} to '{goal.name}'. Progress: {goal.progress_percentage:.1f}%"
                    
                    message_type = "success"
                else:
                    message = "Goal not found!"
                    message_type = "error"
            except Exception as e:
                message = f"Error: {str(e)}"
                message_type = "error"
        else:
            message = "Please select a goal and enter an amount!"
            message_type = "error"
    
    # Handle DELETE request
    if request.method == 'GET' and 'delete' in request.path:
        contribution_id = request.path.split('/')[-2]
        try:
            contribution = GoalContribution.objects.get(id=contribution_id)
            goal = contribution.goal
            
            # Reduce goal amount
            goal.current_amount -= contribution.amount
            goal.save()
            
            contribution.delete()
            
            message = f"Contribution deleted successfully!"
            message_type = "success"
        except Exception as e:
            message = f"Error deleting contribution: {str(e)}"
            message_type = "error"
    
    # Get filter parameters
    filter_goal = request.GET.get('filter_goal')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Get all goals for dropdown
    goals = Goal.objects.all()
    if request.user.is_authenticated:
        goals = goals.filter(user=request.user)
    
    # Calculate progress for each goal
    for goal in goals:
        goal.progress_percentage = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
        goal.remaining = goal.target_amount - goal.current_amount
    
    # Get contributions
    contributions = GoalContribution.objects.all()
    if request.user.is_authenticated:
        contributions = contributions.filter(goal__user=request.user)
    
    # Apply filters
    if filter_goal:
        contributions = contributions.filter(goal_id=filter_goal)
    if start_date:
        contributions = contributions.filter(date__gte=start_date)
    if end_date:
        contributions = contributions.filter(date__lte=end_date)
    
    # Order by most recent first
    contributions = contributions.order_by('-date')
    
    # Calculate totals
    total_contributions = contributions.aggregate(Sum('amount'))['amount__sum'] or 0
    contribution_count = contributions.count()
    active_goals = goals.filter(current_amount__lt=F('target_amount')).count()
    
    # Calculate average contribution
    avg_contribution = contributions.aggregate(Avg('amount'))['amount__avg'] or 0
    
    # Get transactions for linking
    transactions = Transaction.objects.filter(type='expense')
    if request.user.is_authenticated:
        transactions = transactions.filter(user=request.user)
    transactions = transactions.order_by('-date')[:50]
    
    context = {
        'contributions': contributions,
        'goals': goals,
        'transactions': transactions,
        'total_contributions': total_contributions,
        'contribution_count': contribution_count,
        'active_goals': active_goals,
        'avg_contribution': avg_contribution,
        'message': message,
        'message_type': message_type,
        'today': today.isoformat(),
        'filter_goal': filter_goal,
        'start_date': start_date,
        'end_date': end_date,
        'active_page': 'contributions',
        'unread_count': unread_count,
        'currency': 'UGX',
    }
    
    return render(request, 'contributions.html', context)


def bills_page(request):
    """HTML page to manage bills"""
    from django.shortcuts import render
    from django.http import HttpResponse
    from datetime import date, datetime
    from decimal import Decimal
    from dateutil.relativedelta import relativedelta
    
    message = ""
    message_type = ""
    today = date.today()
    
    # Handle POST request (Add bill)
    if request.method == 'POST':
        name = request.POST.get('name')
        amount = Decimal(request.POST.get('amount', 0))
        category_id = request.POST.get('category_id')
        due_day = int(request.POST.get('due_day', 1))
        due_month = request.POST.get('due_month')
        recurrence = request.POST.get('recurrence')
        reminder_days_before = int(request.POST.get('reminder_days_before', 3))
        
        if name and amount > 0:
            bill = Bill.objects.create(
                user=request.user if request.user.is_authenticated else None,
                name=name,
                amount=amount,
                category_id=category_id if category_id else None,
                due_day=due_day,
                due_month=int(due_month) if due_month else None,
                recurrence=recurrence,
                reminder_days_before=reminder_days_before,
                is_active=True
            )
            message = f"Bill '{name}' added successfully!"
            message_type = "success"
        else:
            message = "Please fill all required fields!"
            message_type = "error"
    
    # Handle Mark Paid
    if request.method == 'POST' and 'mark-paid' in request.path:
        bill_id = request.path.split('/')[-2]
        try:
            bill = Bill.objects.get(id=bill_id)
            # Create transaction for this bill payment
            transaction = Transaction.objects.create(
                user=request.user if request.user.is_authenticated else None,
                category=bill.category,
                type='expense',
                amount=bill.amount,
                description=f"Bill payment: {bill.name}",
                date=today,
                is_recurring=False
            )
            
            BillPayment.objects.create(
                bill=bill,
                amount_paid=bill.amount,
                transaction=transaction
            )
            
            # If one-time bill, deactivate it
            if bill.recurrence == 'one-time':
                bill.is_active = False
                bill.save()
            
            message = f"Bill '{bill.name}' marked as paid!"
            message_type = "success"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    # Handle Toggle Active/Inactive
    if request.method == 'POST' and 'toggle' in request.path:
        bill_id = request.path.split('/')[-2]
        try:
            bill = Bill.objects.get(id=bill_id)
            bill.is_active = not bill.is_active
            bill.save()
            status = "activated" if bill.is_active else "deactivated"
            message = f"Bill '{bill.name}' {status}!"
            message_type = "success"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    # Handle DELETE request
    if request.method == 'GET' and 'delete' in request.path:
        bill_id = request.path.split('/')[-2]
        try:
            bill = Bill.objects.get(id=bill_id)
            bill_name = bill.name
            bill.delete()
            message = f"Bill '{bill_name}' deleted successfully!"
            message_type = "success"
        except:
            message = "Bill not found!"
            message_type = "error"
    
    # Get filter parameters
    filter_active = request.GET.get('filter_active')
    filter_recurrence = request.GET.get('filter_recurrence')
    
    # Get bills
    bills = Bill.objects.all()
    if request.user.is_authenticated:
        bills = bills.filter(user=request.user)
    
    # Apply filters
    if filter_active == 'true':
        bills = bills.filter(is_active=True)
    elif filter_active == 'false':
        bills = bills.filter(is_active=False)
    if filter_recurrence:
        bills = bills.filter(recurrence=filter_recurrence)
    
    # Calculate next due date and days until due for each bill
    bills_with_dates = []
    due_this_month_count = 0
    upcoming_bills_list = []
    
    for bill in bills:
        current_year = today.year
        current_month = today.month
        
        if bill.recurrence == 'monthly':
            try:
                next_date = date(current_year, current_month, bill.due_day)
                if next_date < today:
                    if current_month == 12:
                        next_date = date(current_year + 1, 1, bill.due_day)
                    else:
                        next_date = date(current_year, current_month + 1, bill.due_day)
                bill.next_due_date = next_date
            except ValueError:
                bill.next_due_date = None
        elif bill.recurrence == 'yearly' and bill.due_month:
            try:
                next_date = date(current_year, bill.due_month, bill.due_day)
                if next_date < today:
                    next_date = date(current_year + 1, bill.due_month, bill.due_day)
                bill.next_due_date = next_date
            except ValueError:
                bill.next_due_date = None
        elif bill.recurrence == 'quarterly':
            try:
                next_date = date(current_year, current_month, bill.due_day)
                while next_date < today:
                    next_date = next_date + relativedelta(months=3)
                bill.next_due_date = next_date
            except ValueError:
                bill.next_due_date = None
        else:
            bill.next_due_date = None
        
        if bill.next_due_date:
            bill.days_until_due = (bill.next_due_date - today).days
            
            if bill.next_due_date.year == today.year and bill.next_due_date.month == today.month:
                due_this_month_count += 1
            
            if bill.is_active and 0 <= bill.days_until_due <= 7:
                upcoming_bills_list.append(bill)
        else:
            bill.days_until_due = None
        
        bills_with_dates.append(bill)
    
    total_bills = bills.count()
    active_bills = bills.filter(is_active=True).count()
    
    monthly_bills = bills.filter(is_active=True, recurrence='monthly')
    monthly_total = sum(b.amount for b in monthly_bills)
    
    categories = Category.objects.all()
    if request.user.is_authenticated:
        categories = categories.filter(Q(user=request.user) | Q(is_default=True))

    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    context = {
        'bills': bills_with_dates,
        'categories': categories,
        'total_bills': total_bills,
        'active_bills': active_bills,
        'monthly_total': monthly_total,
        'due_this_month': due_this_month_count,
        'upcoming_bills': upcoming_bills_list,
        'message': message,
        'message_type': message_type,
        'filter_active': filter_active,
        'filter_recurrence': filter_recurrence,
        'active_page': 'bills',
        'unread_count': unread_count,
    }
    
    return render(request, 'bills.html', context)


def bill_payments_page(request):
    """HTML page to manage bill payments"""
    from django.shortcuts import render
    from django.db.models import Sum, Count, Avg
    from datetime import date
    from decimal import Decimal
    
    message = ""
    message_type = ""
    today = date.today()
    
    # Handle POST request (Add payment)
    if request.method == 'POST':
        bill_id = request.POST.get('bill_id')
        amount_paid = Decimal(request.POST.get('amount_paid', 0))
        paid_date = request.POST.get('paid_date', today)
        transaction_id = request.POST.get('transaction_id')
        
        if bill_id and amount_paid > 0:
            try:
                bill = Bill.objects.get(id=bill_id)
                
                payment = BillPayment.objects.create(
                    bill=bill,
                    amount_paid=amount_paid,
                    paid_date=paid_date,
                    transaction_id=transaction_id if transaction_id else None
                )
                
                if not transaction_id:
                    transaction = Transaction.objects.create(
                        user=request.user if request.user.is_authenticated else None,
                        category=bill.category,
                        type='expense',
                        amount=amount_paid,
                        description=f"Bill payment: {bill.name}",
                        date=paid_date,
                        is_recurring=False
                    )
                    payment.transaction = transaction
                    payment.save()
                
                message = f"Payment of UGX {amount_paid:,.0f} recorded for '{bill.name}'!"
                message_type = "success"
                
                if bill.recurrence == 'one-time':
                    bill.is_active = False
                    bill.save()
                    
            except Exception as e:
                message = f"Error: {str(e)}"
                message_type = "error"
        else:
            message = "Please select a bill and enter an amount!"
            message_type = "error"
    
    # Handle DELETE request
    if request.method == 'GET' and 'delete' in request.path:
        payment_id = request.path.split('/')[-2]
        try:
            payment = BillPayment.objects.get(id=payment_id)
            bill_name = payment.bill.name
            payment.delete()
            message = f"Payment for '{bill_name}' deleted successfully!"
            message_type = "success"
        except Exception as e:
            message = f"Error deleting payment: {str(e)}"
            message_type = "error"
    
    # Get filter parameters
    filter_bill = request.GET.get('filter_bill')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    bills = Bill.objects.all()
    if request.user.is_authenticated:
        bills = bills.filter(user=request.user)
    
    payments = BillPayment.objects.all()
    if request.user.is_authenticated:
        payments = payments.filter(bill__user=request.user)
    
    if filter_bill:
        payments = payments.filter(bill_id=filter_bill)
    if start_date:
        payments = payments.filter(paid_date__gte=start_date)
    if end_date:
        payments = payments.filter(paid_date__lte=end_date)
    
    payments = payments.order_by('-paid_date')
    
    total_payments = payments.count()
    total_amount = payments.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
    avg_payment = payments.aggregate(Avg('amount_paid'))['amount_paid__avg'] or 0
    
    monthly_payments = payments.filter(
        paid_date__year=today.year,
        paid_date__month=today.month
    )
    monthly_amount = monthly_payments.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
    
    bill_summary = payments.values('bill__name').annotate(
        count=Count('id'),
        total=Sum('amount_paid'),
        avg=Avg('amount_paid')
    ).order_by('-total')
    
    transactions = Transaction.objects.filter(type='expense')
    if request.user.is_authenticated:
        transactions = transactions.filter(user=request.user)
    transactions = transactions.order_by('-date')[:50]

    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    context = {
        'payments': payments,
        'bills': bills,
        'transactions': transactions,
        'bill_summary': bill_summary,
        'total_payments': total_payments,
        'total_amount': total_amount,
        'avg_payment': avg_payment,
        'monthly_amount': monthly_amount,
        'message': message,
        'message_type': message_type,
        'today': today.isoformat(),
        'filter_bill': filter_bill,
        'start_date': start_date,
        'end_date': end_date,
        'active_page': 'bill_payments',
        'unread_count': unread_count,
    }
    
    return render(request, 'bill_payments.html', context)


def notifications_page(request):
    """HTML page to manage notifications"""
    from django.shortcuts import render
    from datetime import date, timedelta
    
    message = ""
    message_type = ""
    today = date.today()
    week_ago = today - timedelta(days=7)
    
    # Handle POST request (Mark as read/unread)
    if request.method == 'POST':
        if 'mark-all-read' in request.path:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
            message = "All notifications marked as read!"
            message_type = "success"
    
    if request.method == 'POST' and 'mark-read' in request.path:
        notification_id = request.path.split('/')[-2]
        try:
            notification = Notification.objects.get(id=notification_id)
            notification.is_read = True
            notification.save()
            message = "Notification marked as read!"
            message_type = "success"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    if request.method == 'POST' and 'mark-unread' in request.path:
        notification_id = request.path.split('/')[-2]
        try:
            notification = Notification.objects.get(id=notification_id)
            notification.is_read = False
            notification.save()
            message = "Notification marked as unread!"
            message_type = "success"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    if request.method == 'GET' and 'delete' in request.path:
        notification_id = request.path.split('/')[-2]
        try:
            notification = Notification.objects.get(id=notification_id)
            notification.delete()
            message = "Notification deleted successfully!"
            message_type = "success"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    filter_type = request.GET.get('filter_type')
    filter_status = request.GET.get('filter_status')
    
    notifications = Notification.objects.all()
    if request.user.is_authenticated:
        notifications = notifications.filter(user=request.user)
    
    if filter_type:
        notifications = notifications.filter(type=filter_type)
    if filter_status == 'unread':
        notifications = notifications.filter(is_read=False)
    elif filter_status == 'read':
        notifications = notifications.filter(is_read=True)
    
    notifications = notifications.order_by('-created_at')
    
    total_count = notifications.count()
    unread_count = notifications.filter(is_read=False).count()
    read_count = notifications.filter(is_read=True).count()
    weekly_count = notifications.filter(created_at__date__gte=week_ago).count()
    
    for notification in notifications:
        if notification.type == 'budget_alert':
            notification.data['navigation_url'] = '/api/budgets-page/'
        elif notification.type == 'bill_reminder':
            notification.data['navigation_url'] = '/api/bills-page/'
        elif notification.type == 'goal_milestone':
            notification.data['navigation_url'] = '/api/goals-page/'
        elif notification.type == 'weekly_report':
            notification.data['navigation_url'] = '/api/transactions-page/'
        else:
            notification.data['navigation_url'] = '#'
        notification.save()
    
    context = {
        'notifications': notifications,
        'total_count': total_count,
        'unread_count': unread_count,
        'read_count': read_count,
        'weekly_count': weekly_count,
        'message': message,
        'message_type': message_type,
        'filter_type': filter_type,
        'filter_status': filter_status,
        'active_page': 'notifications',
        'unread_count': unread_count,
    }
    
    return render(request, 'notifications.html', context)


def settings_page(request):
    """HTML page to manage app settings"""
    from django.shortcuts import render
    
    message = ""
    message_type = ""
    
    if request.user.is_authenticated:
        settings, created = AppSetting.objects.get_or_create(user=request.user)
    else:
        settings = AppSetting()
    
    if request.method == 'POST':
        try:
            settings.theme = request.POST.get('theme', 'light')
            settings.language = request.POST.get('language', 'en')
            settings.currency = request.POST.get('currency', 'UGX')
            settings.notifications_enabled = request.POST.get('notifications_enabled') == 'on'
            settings.budget_alerts = request.POST.get('budget_alerts') == 'on'
            settings.bill_reminders = request.POST.get('bill_reminders') == 'on'
            settings.goal_milestones = request.POST.get('goal_milestones') == 'on'
            settings.weekly_summary = request.POST.get('weekly_summary') == 'on'
            settings.auto_lock_minutes = int(request.POST.get('auto_lock_minutes', 5))
            settings.biometric_login = request.POST.get('biometric_login') == 'on'
            
            if request.user.is_authenticated:
                settings.save()
            
            message = "Settings saved successfully!"
            message_type = "success"
        except Exception as e:
            message = f"Error saving settings: {str(e)}"
            message_type = "error"

    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    context = {
        'settings': settings,
        'message': message,
        'message_type': message_type,
        'active_page': 'settings',
        'unread_count': unread_count,
    }
    
    return render(request, 'app_settings.html', context)


def reset_settings(request):
    """Reset app settings to default values"""
    from django.shortcuts import redirect
    
    if request.user.is_authenticated:
        settings, created = AppSetting.objects.get_or_create(user=request.user)
        settings.theme = 'light'
        settings.language = 'en'
        settings.currency = 'UGX'
        settings.notifications_enabled = True
        settings.budget_alerts = True
        settings.bill_reminders = True
        settings.goal_milestones = True
        settings.weekly_summary = True
        settings.auto_lock_minutes = 5
        settings.biometric_login = False
        settings.save()
    
    return redirect('settings_page')


def dashboard_page(request):
    """Main dashboard page"""
    from django.shortcuts import render
    from django.db.models import Sum
    from datetime import date, timedelta
    from decimal import Decimal
    
    today = date.today()
    current_month = today.month
    current_year = today.year
    
    class GuestUser:
        username = "Guest"
        full_name = "Guest User"
        is_authenticated = False
    
    if request.user.is_authenticated:
        user_obj = request.user
        try:
            settings = AppSetting.objects.get(user=request.user)
            currency = settings.currency
        except:
            currency = "UGX"
    else:
        user_obj = GuestUser()
        currency = "UGX"
    
    monthly_transactions = Transaction.objects.filter(
        date__year=current_year,
        date__month=current_month
    )
    if request.user.is_authenticated:
        monthly_transactions = monthly_transactions.filter(user=request.user)
    
    total_income = monthly_transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    total_expense = monthly_transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    balance = total_income - total_expense
    savings_rate = (balance / total_income * 100) if total_income > 0 else 0
    
    recent_transactions = monthly_transactions.order_by('-date')[:10]
    
    top_categories = monthly_transactions.filter(type='expense').values(
        'category__name', 'category__icon'
    ).annotate(total=Sum('amount')).order_by('-total')[:5]
    
    active_goals = Goal.objects.filter(target_amount__gt=models.F('current_amount'))
    if request.user.is_authenticated:
        active_goals = active_goals.filter(user=request.user)
    active_goals = active_goals[:5]
    
    for goal in active_goals:
        goal.progress_percentage = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
    
    upcoming_bills = []
    bills = Bill.objects.filter(is_active=True)
    if request.user.is_authenticated:
        bills = bills.filter(user=request.user)
    
    for bill in bills:
        if bill.recurrence == 'monthly':
            try:
                next_date = date(current_year, current_month, bill.due_day)
                if next_date < today:
                    if current_month == 12:
                        next_date = date(current_year + 1, 1, bill.due_day)
                    else:
                        next_date = date(current_year, current_month + 1, bill.due_day)
                bill.next_due_date = next_date
                bill.days_until_due = (next_date - today).days
                if 0 <= bill.days_until_due <= 7:
                    upcoming_bills.append(bill)
            except ValueError:
                pass
    
    budgets = Budget.objects.filter(month=current_month, year=current_year)
    if request.user.is_authenticated:
        budgets = budgets.filter(user=request.user)
    
    for budget in budgets:
        spent = Transaction.objects.filter(
            category=budget.category,
            type='expense',
            date__year=current_year,
            date__month=current_month
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        budget.spent = spent
        budget.remaining = budget.amount - spent
        budget.usage_percentage = (spent / budget.amount * 100) if budget.amount > 0 else 0
    
    alerts = []
    
    for budget in budgets:
        if budget.usage_percentage >= 80:
            alerts.append({
                'type': 'budget',
                'title': f'Budget Alert: {budget.category.name}',
                'message': f'You have used {budget.usage_percentage:.0f}% of your {budget.category.name} budget'
            })
    
    for goal in active_goals:
        if goal.progress_percentage >= 50 and goal.progress_percentage < 55:
            alerts.append({
                'type': 'goal',
                'title': f'Goal Milestone: {goal.name}',
                'message': f'You are 50% of the way to your goal! Keep going!'
            })
    
    for bill in upcoming_bills:
        if hasattr(bill, 'days_until_due') and bill.days_until_due <= bill.reminder_days_before:
            alerts.append({
                'type': 'bill',
                'title': f'Bill Reminder: {bill.name}',
                'message': f'{bill.name} is due in {bill.days_until_due} days'
            })
    
    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    context = {
        'currency': currency,
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
        'savings_rate': savings_rate,
        'recent_transactions': recent_transactions,
        'top_categories': top_categories,
        'active_goals': active_goals,
        'upcoming_bills': upcoming_bills[:5],
        'budgets': budgets[:5],
        'alerts': alerts[:5],
        'active_page': 'dashboard',
        'unread_count': unread_count,
        'user': user_obj,
    }
    
    return render(request, 'dashboard.html', context)


def test_page(request):
    """Simple test page"""
    return render(request, 'test.html', {'test_variable': 'Hello World!'})

def contributions_page(request):
    """HTML page to manage goal contributions"""
    from django.shortcuts import render
    from django.db.models import Sum, Avg, F
    from datetime import date
    from decimal import Decimal
    from .models import Goal, GoalContribution, Transaction, Notification
    
    message = ""
    message_type = ""
    today = date.today()
    
    # Get unread count
    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    # Handle POST request (Add contribution)
    if request.method == 'POST':
        goal_id = request.POST.get('goal_id')
        amount = Decimal(request.POST.get('amount', 0))
        contribution_date = request.POST.get('date', today)
        transaction_id = request.POST.get('transaction_id')
        
        if goal_id and amount > 0:
            try:
                goal = Goal.objects.get(id=goal_id)
                if request.user.is_authenticated:
                    goal = Goal.objects.filter(id=goal_id, user=request.user).first()
                
                if goal:
                    # Create contribution
                    contribution = GoalContribution.objects.create(
                        goal=goal,
                        amount=amount,
                        date=contribution_date,
                        transaction_id=transaction_id if transaction_id else None
                    )
                    
                    # Update goal current amount
                    goal.current_amount += amount
                    goal.save()
                    
                    # Check if goal is achieved
                    if goal.current_amount >= goal.target_amount:
                        Notification.objects.create(
                            user=request.user if request.user.is_authenticated else None,
                            type='goal_milestone',
                            title='Goal Achieved! 🎉',
                            message=f'Congratulations! You have achieved your goal: {goal.name}',
                            data={'goal_id': goal.id}
                        )
                        message = f"🎉 Congratulations! You've achieved your goal '{goal.name}'!"
                    else:
                        message = f"Added UGX {amount:,.0f} to '{goal.name}'. Progress: {goal.progress_percentage:.1f}%"
                    
                    message_type = "success"
                else:
                    message = "Goal not found!"
                    message_type = "error"
            except Exception as e:
                message = f"Error: {str(e)}"
                message_type = "error"
        else:
            message = "Please select a goal and enter an amount!"
            message_type = "error"
    
    # Handle DELETE request
    if request.method == 'GET' and 'delete' in request.path:
        contribution_id = request.path.split('/')[-2]
        try:
            contribution = GoalContribution.objects.get(id=contribution_id)
            goal = contribution.goal
            
            # Reduce goal amount
            goal.current_amount -= contribution.amount
            goal.save()
            
            contribution.delete()
            
            message = f"Contribution deleted successfully!"
            message_type = "success"
        except Exception as e:
            message = f"Error deleting contribution: {str(e)}"
            message_type = "error"
    
    # Get filter parameters
    filter_goal = request.GET.get('filter_goal')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Get all goals for dropdown
    goals = Goal.objects.all()
    if request.user.is_authenticated:
        goals = goals.filter(user=request.user)
    
    # Calculate progress for each goal
    for goal in goals:
        goal.progress_percentage = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
        goal.remaining = goal.target_amount - goal.current_amount
    
    # Get contributions
    contributions = GoalContribution.objects.all()
    if request.user.is_authenticated:
        contributions = contributions.filter(goal__user=request.user)
    
    # Apply filters
    if filter_goal:
        contributions = contributions.filter(goal_id=filter_goal)
    if start_date:
        contributions = contributions.filter(date__gte=start_date)
    if end_date:
        contributions = contributions.filter(date__lte=end_date)
    
    # Order by most recent first
    contributions = contributions.order_by('-date')
    
    # Calculate totals
    total_contributions = contributions.aggregate(Sum('amount'))['amount__sum'] or 0
    contribution_count = contributions.count()
    active_goals = goals.filter(current_amount__lt=F('target_amount')).count()
    
    # Calculate average contribution
    avg_contribution = contributions.aggregate(Avg('amount'))['amount__avg'] or 0
    
    # Get transactions for linking
    transactions = Transaction.objects.filter(type='expense')
    if request.user.is_authenticated:
        transactions = transactions.filter(user=request.user)
    transactions = transactions.order_by('-date')[:50]
    
    context = {
        'contributions': contributions,
        'goals': goals,
        'transactions': transactions,
        'total_contributions': total_contributions,
        'contribution_count': contribution_count,
        'active_goals': active_goals,
        'avg_contribution': avg_contribution,
        'message': message,
        'message_type': message_type,
        'today': today.isoformat(),
        'filter_goal': filter_goal,
        'start_date': start_date,
        'end_date': end_date,
        'active_page': 'contributions',
        'unread_count': unread_count,
        'currency': 'UGX',
    }
    
    return render(request, 'contributions.html', context)


def bills_page(request):
    """HTML page to manage bills"""
    from django.shortcuts import render
    from django.http import HttpResponse
    from datetime import date, datetime
    from decimal import Decimal
    from dateutil.relativedelta import relativedelta
    
    message = ""
    message_type = ""
    today = date.today()
    
    # Handle POST request (Add bill)
    if request.method == 'POST':
        name = request.POST.get('name')
        amount = Decimal(request.POST.get('amount', 0))
        category_id = request.POST.get('category_id')
        due_day = int(request.POST.get('due_day', 1))
        due_month = request.POST.get('due_month')
        recurrence = request.POST.get('recurrence')
        reminder_days_before = int(request.POST.get('reminder_days_before', 3))
        
        if name and amount > 0:
            bill = Bill.objects.create(
                user=request.user if request.user.is_authenticated else None,
                name=name,
                amount=amount,
                category_id=category_id if category_id else None,
                due_day=due_day,
                due_month=int(due_month) if due_month else None,
                recurrence=recurrence,
                reminder_days_before=reminder_days_before,
                is_active=True
            )
            message = f"Bill '{name}' added successfully!"
            message_type = "success"
        else:
            message = "Please fill all required fields!"
            message_type = "error"
    
    # Handle Mark Paid
    if request.method == 'POST' and 'mark-paid' in request.path:
        bill_id = request.path.split('/')[-2]
        try:
            bill = Bill.objects.get(id=bill_id)
            # Create transaction for this bill payment
            transaction = Transaction.objects.create(
                user=request.user if request.user.is_authenticated else None,
                category=bill.category,
                type='expense',
                amount=bill.amount,
                description=f"Bill payment: {bill.name}",
                date=today,
                is_recurring=False
            )
            
            BillPayment.objects.create(
                bill=bill,
                amount_paid=bill.amount,
                transaction=transaction
            )
            
            # If one-time bill, deactivate it
            if bill.recurrence == 'one-time':
                bill.is_active = False
                bill.save()
            
            message = f"Bill '{bill.name}' marked as paid!"
            message_type = "success"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    # Handle Toggle Active/Inactive
    if request.method == 'POST' and 'toggle' in request.path:
        bill_id = request.path.split('/')[-2]
        try:
            bill = Bill.objects.get(id=bill_id)
            bill.is_active = not bill.is_active
            bill.save()
            status = "activated" if bill.is_active else "deactivated"
            message = f"Bill '{bill.name}' {status}!"
            message_type = "success"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    # Handle DELETE request
    if request.method == 'GET' and 'delete' in request.path:
        bill_id = request.path.split('/')[-2]
        try:
            bill = Bill.objects.get(id=bill_id)
            bill_name = bill.name
            bill.delete()
            message = f"Bill '{bill_name}' deleted successfully!"
            message_type = "success"
        except:
            message = "Bill not found!"
            message_type = "error"
    
    # Get filter parameters
    filter_active = request.GET.get('filter_active')
    filter_recurrence = request.GET.get('filter_recurrence')
    
    # Get bills
    bills = Bill.objects.all()
    if request.user.is_authenticated:
        bills = bills.filter(user=request.user)
    
    # Apply filters
    if filter_active == 'true':
        bills = bills.filter(is_active=True)
    elif filter_active == 'false':
        bills = bills.filter(is_active=False)
    if filter_recurrence:
        bills = bills.filter(recurrence=filter_recurrence)
    
    # Calculate next due date and days until due for each bill
    bills_with_dates = []
    due_this_month_count = 0
    upcoming_bills_list = []
    
    for bill in bills:
        current_year = today.year
        current_month = today.month
        
        if bill.recurrence == 'monthly':
            try:
                next_date = date(current_year, current_month, bill.due_day)
                if next_date < today:
                    if current_month == 12:
                        next_date = date(current_year + 1, 1, bill.due_day)
                    else:
                        next_date = date(current_year, current_month + 1, bill.due_day)
                bill.next_due_date = next_date
            except ValueError:
                bill.next_due_date = None
        elif bill.recurrence == 'yearly' and bill.due_month:
            try:
                next_date = date(current_year, bill.due_month, bill.due_day)
                if next_date < today:
                    next_date = date(current_year + 1, bill.due_month, bill.due_day)
                bill.next_due_date = next_date
            except ValueError:
                bill.next_due_date = None
        elif bill.recurrence == 'quarterly':
            try:
                next_date = date(current_year, current_month, bill.due_day)
                while next_date < today:
                    next_date = next_date + relativedelta(months=3)
                bill.next_due_date = next_date
            except ValueError:
                bill.next_due_date = None
        else:
            bill.next_due_date = None
        
        if bill.next_due_date:
            bill.days_until_due = (bill.next_due_date - today).days
            
            if bill.next_due_date.year == today.year and bill.next_due_date.month == today.month:
                due_this_month_count += 1
            
            if bill.is_active and 0 <= bill.days_until_due <= 7:
                upcoming_bills_list.append(bill)
        else:
            bill.days_until_due = None
        
        bills_with_dates.append(bill)
    
    total_bills = bills.count()
    active_bills = bills.filter(is_active=True).count()
    
    monthly_bills = bills.filter(is_active=True, recurrence='monthly')
    monthly_total = sum(b.amount for b in monthly_bills)
    
    categories = Category.objects.all()
    if request.user.is_authenticated:
        categories = categories.filter(Q(user=request.user) | Q(is_default=True))

    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    context = {
        'bills': bills_with_dates,
        'categories': categories,
        'total_bills': total_bills,
        'active_bills': active_bills,
        'monthly_total': monthly_total,
        'due_this_month': due_this_month_count,
        'upcoming_bills': upcoming_bills_list,
        'message': message,
        'message_type': message_type,
        'filter_active': filter_active,
        'filter_recurrence': filter_recurrence,
        'active_page': 'bills',
        'unread_count': unread_count,
    }
    
    return render(request, 'bills.html', context)


def bill_payments_page(request):
    """HTML page to manage bill payments"""
    from django.shortcuts import render
    from django.db.models import Sum, Count, Avg
    from datetime import date
    from decimal import Decimal
    
    message = ""
    message_type = ""
    today = date.today()
    
    # Handle POST request (Add payment)
    if request.method == 'POST':
        bill_id = request.POST.get('bill_id')
        amount_paid = Decimal(request.POST.get('amount_paid', 0))
        paid_date = request.POST.get('paid_date', today)
        transaction_id = request.POST.get('transaction_id')
        
        if bill_id and amount_paid > 0:
            try:
                bill = Bill.objects.get(id=bill_id)
                
                payment = BillPayment.objects.create(
                    bill=bill,
                    amount_paid=amount_paid,
                    paid_date=paid_date,
                    transaction_id=transaction_id if transaction_id else None
                )
                
                if not transaction_id:
                    transaction = Transaction.objects.create(
                        user=request.user if request.user.is_authenticated else None,
                        category=bill.category,
                        type='expense',
                        amount=amount_paid,
                        description=f"Bill payment: {bill.name}",
                        date=paid_date,
                        is_recurring=False
                    )
                    payment.transaction = transaction
                    payment.save()
                
                message = f"Payment of UGX {amount_paid:,.0f} recorded for '{bill.name}'!"
                message_type = "success"
                
                if bill.recurrence == 'one-time':
                    bill.is_active = False
                    bill.save()
                    
            except Exception as e:
                message = f"Error: {str(e)}"
                message_type = "error"
        else:
            message = "Please select a bill and enter an amount!"
            message_type = "error"
    
    # Handle DELETE request
    if request.method == 'GET' and 'delete' in request.path:
        payment_id = request.path.split('/')[-2]
        try:
            payment = BillPayment.objects.get(id=payment_id)
            bill_name = payment.bill.name
            payment.delete()
            message = f"Payment for '{bill_name}' deleted successfully!"
            message_type = "success"
        except Exception as e:
            message = f"Error deleting payment: {str(e)}"
            message_type = "error"
    
    # Get filter parameters
    filter_bill = request.GET.get('filter_bill')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    bills = Bill.objects.all()
    if request.user.is_authenticated:
        bills = bills.filter(user=request.user)
    
    payments = BillPayment.objects.all()
    if request.user.is_authenticated:
        payments = payments.filter(bill__user=request.user)
    
    if filter_bill:
        payments = payments.filter(bill_id=filter_bill)
    if start_date:
        payments = payments.filter(paid_date__gte=start_date)
    if end_date:
        payments = payments.filter(paid_date__lte=end_date)
    
    payments = payments.order_by('-paid_date')
    
    total_payments = payments.count()
    total_amount = payments.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
    avg_payment = payments.aggregate(Avg('amount_paid'))['amount_paid__avg'] or 0
    
    monthly_payments = payments.filter(
        paid_date__year=today.year,
        paid_date__month=today.month
    )
    monthly_amount = monthly_payments.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
    
    bill_summary = payments.values('bill__name').annotate(
        count=Count('id'),
        total=Sum('amount_paid'),
        avg=Avg('amount_paid')
    ).order_by('-total')
    
    transactions = Transaction.objects.filter(type='expense')
    if request.user.is_authenticated:
        transactions = transactions.filter(user=request.user)
    transactions = transactions.order_by('-date')[:50]

    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    context = {
        'payments': payments,
        'bills': bills,
        'transactions': transactions,
        'bill_summary': bill_summary,
        'total_payments': total_payments,
        'total_amount': total_amount,
        'avg_payment': avg_payment,
        'monthly_amount': monthly_amount,
        'message': message,
        'message_type': message_type,
        'today': today.isoformat(),
        'filter_bill': filter_bill,
        'start_date': start_date,
        'end_date': end_date,
        'active_page': 'bill_payments',
        'unread_count': unread_count,
    }
    
    return render(request, 'bill_payments.html', context)


def notifications_page(request):
    """HTML page to manage notifications"""
    from django.shortcuts import render
    from datetime import date, timedelta
    
    message = ""
    message_type = ""
    today = date.today()
    week_ago = today - timedelta(days=7)
    
    # Handle POST request (Mark as read/unread)
    if request.method == 'POST':
        if 'mark-all-read' in request.path:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
            message = "All notifications marked as read!"
            message_type = "success"
    
    if request.method == 'POST' and 'mark-read' in request.path:
        notification_id = request.path.split('/')[-2]
        try:
            notification = Notification.objects.get(id=notification_id)
            notification.is_read = True
            notification.save()
            message = "Notification marked as read!"
            message_type = "success"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    if request.method == 'POST' and 'mark-unread' in request.path:
        notification_id = request.path.split('/')[-2]
        try:
            notification = Notification.objects.get(id=notification_id)
            notification.is_read = False
            notification.save()
            message = "Notification marked as unread!"
            message_type = "success"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    if request.method == 'GET' and 'delete' in request.path:
        notification_id = request.path.split('/')[-2]
        try:
            notification = Notification.objects.get(id=notification_id)
            notification.delete()
            message = "Notification deleted successfully!"
            message_type = "success"
        except Exception as e:
            message = f"Error: {str(e)}"
            message_type = "error"
    
    filter_type = request.GET.get('filter_type')
    filter_status = request.GET.get('filter_status')
    
    notifications = Notification.objects.all()
    if request.user.is_authenticated:
        notifications = notifications.filter(user=request.user)
    
    if filter_type:
        notifications = notifications.filter(type=filter_type)
    if filter_status == 'unread':
        notifications = notifications.filter(is_read=False)
    elif filter_status == 'read':
        notifications = notifications.filter(is_read=True)
    
    notifications = notifications.order_by('-created_at')
    
    total_count = notifications.count()
    unread_count = notifications.filter(is_read=False).count()
    read_count = notifications.filter(is_read=True).count()
    weekly_count = notifications.filter(created_at__date__gte=week_ago).count()
    
    for notification in notifications:
        if notification.type == 'budget_alert':
            notification.data['navigation_url'] = '/api/budgets-page/'
        elif notification.type == 'bill_reminder':
            notification.data['navigation_url'] = '/api/bills-page/'
        elif notification.type == 'goal_milestone':
            notification.data['navigation_url'] = '/api/goals-page/'
        elif notification.type == 'weekly_report':
            notification.data['navigation_url'] = '/api/transactions-page/'
        else:
            notification.data['navigation_url'] = '#'
        notification.save()
    
    context = {
        'notifications': notifications,
        'total_count': total_count,
        'unread_count': unread_count,
        'read_count': read_count,
        'weekly_count': weekly_count,
        'message': message,
        'message_type': message_type,
        'filter_type': filter_type,
        'filter_status': filter_status,
        'active_page': 'notifications',
        'unread_count': unread_count,
    }
    
    return render(request, 'notifications.html', context)


def settings_page(request):
    """HTML page to manage app settings"""
    from django.shortcuts import render
    
    message = ""
    message_type = ""
    
    if request.user.is_authenticated:
        settings, created = AppSetting.objects.get_or_create(user=request.user)
    else:
        settings = AppSetting()
    
    if request.method == 'POST':
        try:
            settings.theme = request.POST.get('theme', 'light')
            settings.language = request.POST.get('language', 'en')
            settings.currency = request.POST.get('currency', 'UGX')
            settings.notifications_enabled = request.POST.get('notifications_enabled') == 'on'
            settings.budget_alerts = request.POST.get('budget_alerts') == 'on'
            settings.bill_reminders = request.POST.get('bill_reminders') == 'on'
            settings.goal_milestones = request.POST.get('goal_milestones') == 'on'
            settings.weekly_summary = request.POST.get('weekly_summary') == 'on'
            settings.auto_lock_minutes = int(request.POST.get('auto_lock_minutes', 5))
            settings.biometric_login = request.POST.get('biometric_login') == 'on'
            
            if request.user.is_authenticated:
                settings.save()
            
            message = "Settings saved successfully!"
            message_type = "success"
        except Exception as e:
            message = f"Error saving settings: {str(e)}"
            message_type = "error"

    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    context = {
        'settings': settings,
        'message': message,
        'message_type': message_type,
        'active_page': 'settings',
        'unread_count': unread_count,
    }
    
    return render(request, 'app_settings.html', context)


def reset_settings(request):
    """Reset app settings to default values"""
    from django.shortcuts import redirect
    
    if request.user.is_authenticated:
        settings, created = AppSetting.objects.get_or_create(user=request.user)
        settings.theme = 'light'
        settings.language = 'en'
        settings.currency = 'UGX'
        settings.notifications_enabled = True
        settings.budget_alerts = True
        settings.bill_reminders = True
        settings.goal_milestones = True
        settings.weekly_summary = True
        settings.auto_lock_minutes = 5
        settings.biometric_login = False
        settings.save()
    
    return redirect('settings_page')


def dashboard_page(request):
    """Main dashboard page"""
    from django.shortcuts import render
    from django.db.models import Sum
    from datetime import date, timedelta
    from decimal import Decimal
    
    today = date.today()
    current_month = today.month
    current_year = today.year
    
    class GuestUser:
        username = "Guest"
        full_name = "Guest User"
        is_authenticated = False
    
    if request.user.is_authenticated:
        user_obj = request.user
        try:
            settings = AppSetting.objects.get(user=request.user)
            currency = settings.currency
        except:
            currency = "UGX"
    else:
        user_obj = GuestUser()
        currency = "UGX"
    
    monthly_transactions = Transaction.objects.filter(
        date__year=current_year,
        date__month=current_month
    )
    if request.user.is_authenticated:
        monthly_transactions = monthly_transactions.filter(user=request.user)
    
    total_income = monthly_transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    total_expense = monthly_transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    balance = total_income - total_expense
    savings_rate = (balance / total_income * 100) if total_income > 0 else 0
    
    recent_transactions = monthly_transactions.order_by('-date')[:10]
    
    top_categories = monthly_transactions.filter(type='expense').values(
        'category__name', 'category__icon'
    ).annotate(total=Sum('amount')).order_by('-total')[:5]
    
    active_goals = Goal.objects.filter(target_amount__gt=models.F('current_amount'))
    if request.user.is_authenticated:
        active_goals = active_goals.filter(user=request.user)
    active_goals = active_goals[:5]
    
    for goal in active_goals:
        goal.progress_percentage = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
    
    upcoming_bills = []
    bills = Bill.objects.filter(is_active=True)
    if request.user.is_authenticated:
        bills = bills.filter(user=request.user)
    
    for bill in bills:
        if bill.recurrence == 'monthly':
            try:
                next_date = date(current_year, current_month, bill.due_day)
                if next_date < today:
                    if current_month == 12:
                        next_date = date(current_year + 1, 1, bill.due_day)
                    else:
                        next_date = date(current_year, current_month + 1, bill.due_day)
                bill.next_due_date = next_date
                bill.days_until_due = (next_date - today).days
                if 0 <= bill.days_until_due <= 7:
                    upcoming_bills.append(bill)
            except ValueError:
                pass
    
    budgets = Budget.objects.filter(month=current_month, year=current_year)
    if request.user.is_authenticated:
        budgets = budgets.filter(user=request.user)
    
    for budget in budgets:
        spent = Transaction.objects.filter(
            category=budget.category,
            type='expense',
            date__year=current_year,
            date__month=current_month
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        budget.spent = spent
        budget.remaining = budget.amount - spent
        budget.usage_percentage = (spent / budget.amount * 100) if budget.amount > 0 else 0
    
    alerts = []
    
    for budget in budgets:
        if budget.usage_percentage >= 80:
            alerts.append({
                'type': 'budget',
                'title': f'Budget Alert: {budget.category.name}',
                'message': f'You have used {budget.usage_percentage:.0f}% of your {budget.category.name} budget'
            })
    
    for goal in active_goals:
        if goal.progress_percentage >= 50 and goal.progress_percentage < 55:
            alerts.append({
                'type': 'goal',
                'title': f'Goal Milestone: {goal.name}',
                'message': f'You are 50% of the way to your goal! Keep going!'
            })
    
    for bill in upcoming_bills:
        if hasattr(bill, 'days_until_due') and bill.days_until_due <= bill.reminder_days_before:
            alerts.append({
                'type': 'bill',
                'title': f'Bill Reminder: {bill.name}',
                'message': f'{bill.name} is due in {bill.days_until_due} days'
            })
    
    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    context = {
        'currency': currency,
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
        'savings_rate': savings_rate,
        'recent_transactions': recent_transactions,
        'top_categories': top_categories,
        'active_goals': active_goals,
        'upcoming_bills': upcoming_bills[:5],
        'budgets': budgets[:5],
        'alerts': alerts[:5],
        'active_page': 'dashboard',
        'unread_count': unread_count,
        'user': user_obj,
    }
    
    return render(request, 'dashboard.html', context)


def test_page(request):
    """Simple test page"""
    return render(request, 'test.html', {'test_variable': 'Hello World!'})