from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('health/', views.health, name='health'),
    path('robots.txt', views.robots, name='robots'),

    # Legal pages. One view, four routes — the URL name is `legal_<slug>`, which
    # the shared template relies on to cross-link them.
    path('privacy/', views.legal_page, {'slug': 'privacy'}, name='legal_privacy'),
    path('cookies/', views.legal_page, {'slug': 'cookies'}, name='legal_cookies'),
    path('terms/', views.legal_page, {'slug': 'terms'}, name='legal_terms'),
    path('accessibility/', views.legal_page, {'slug': 'accessibility'}, name='legal_accessibility'),
]
