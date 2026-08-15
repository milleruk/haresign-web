from django.contrib import admin

from .models import Subscriber


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'active', 'source', 'subscribed_at')
    list_filter = ('active', 'source', 'subscribed_at')
    search_fields = ('email', 'name')
    readonly_fields = ('unsubscribe_token', 'subscribed_at')
    ordering = ('-subscribed_at',)

    # Deliberately absent: any bulk "email these people" action. Sending is not
    # this application's job (see README, "Newsletter") and an admin action that
    # sends is how a list gets mailed twice from two systems.
    actions = None
