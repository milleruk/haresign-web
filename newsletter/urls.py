from django.urls import path

from . import views

app_name = 'newsletter'

urlpatterns = [
    path('subscribe/', views.subscribe, name='subscribe'),
    # UUID, not a signed pk: the token is the only credential the link carries,
    # and it must not be guessable from a subscriber count.
    path('unsubscribe/<uuid:token>/', views.unsubscribe, name='unsubscribe'),
]
