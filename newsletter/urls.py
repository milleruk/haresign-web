from django.urls import path

from . import views

app_name = 'newsletter'

urlpatterns = [
    # The public archive. `/newsletter/` rather than `/newsletters/`: the
    # subscribe and unsubscribe routes already live under this prefix, and one
    # newsletter noun beats two.
    path('', views.issue_index, name='issues'),

    path('subscribe/', views.subscribe, name='subscribe'),
    # UUID, not a signed pk: the token is the only credential the link carries,
    # and it must not be guessable from a subscriber count.
    path('unsubscribe/<uuid:token>/', views.unsubscribe, name='unsubscribe'),

    # Last, so it cannot shadow the fixed routes above.
    path('<slug:slug>/', views.issue_detail, name='issue'),
]
