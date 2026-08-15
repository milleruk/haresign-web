from django.contrib import admin

from .models import Issue, Subscriber


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


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('subject', 'sent_at', 'send_count', 'is_draft')
    list_filter = ('sent_at',)
    search_fields = ('title', 'subject', 'body_html')
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ('articles',)
    readonly_fields = ('legacy_id', 'legacy_path', 'body_source')
    date_hierarchy = 'sent_at'

    fieldsets = (
        (None, {'fields': ('title', 'slug', 'subject')}),
        ('Content', {'fields': ('body_html', 'articles')}),
        ('Sending', {
            'fields': ('sent_at', 'send_count'),
            'description': 'A record of what the monolith sent. Setting a date '
                           'here publishes the issue to the archive — it does '
                           '<strong>not</strong> send anything, because this '
                           'application has no send path.',
        }),
        ('Dates', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
        ('Migration provenance', {
            'fields': ('legacy_id', 'legacy_path', 'body_source'),
            'classes': ('collapse',),
            'description': 'Read-only. body_source is the monolith HTML before '
                           'the import rewrote links; it is never rendered.',
        }),
    )

    # Same rule as subscribers: nothing in this admin may send.
    actions = None
