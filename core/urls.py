
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('production/planning/', views.production_gantt, name='planning'),
    path('reporting/', views.reporting, name='reporting'),
    path('stock/import/', views.import_stock_view, name='import_stock'), # NOUVELLE ROUTE
]
