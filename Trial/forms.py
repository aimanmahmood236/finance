from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class UserForm(UserCreationForm):
    full_name = forms.CharField(max_length=255, required=True)
    email = forms.EmailField(required=True)
    monthly_income = forms.DecimalField(max_digits=12, decimal_places=2, required=False)
    currency = forms.CharField(max_length=3, initial="UGX", required=False)
    
    class Meta:
        model = User
        fields = ['username', 'full_name', 'email', 'password1', 'password2', 'monthly_income', 'currency']
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.full_name = self.cleaned_data['full_name']
        user.email = self.cleaned_data['email']
        user.monthly_income = self.cleaned_data['monthly_income']
        user.currency = self.cleaned_data['currency']
        if commit:
            user.save()
        return user