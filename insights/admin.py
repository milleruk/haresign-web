"""Django Admin as the Insights publishing backend.

Good enough to publish from without introducing a CMS. The list view answers the
two questions an editor actually has — what is live, and what is waiting — and
`is_live` is shown as its own column because "status: Published" alone does not
mean visible when the date is in the future.
"""
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Article, Category, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'article_count']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']

    @admin.display(description='Articles')
    def article_count(self, obj):
        return obj.articles.count()


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'article_count']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']

    @admin.display(description='Articles')
    def article_count(self, obj):
        return obj.articles.count()


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'visibility', 'status', 'published_at',
                    'is_featured', 'author_name']
    list_filter = ['status', 'is_featured', 'categories', 'tags', 'published_at']
    list_editable = ['is_featured']
    search_fields = ['title', 'summary', 'body', 'author_name', 'slug']
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['categories', 'tags']
    date_hierarchy = 'published_at'
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-published_at', '-created_at']
    save_on_top = True

    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'kicker', 'summary'),
        }),
        ('Article', {
            'fields': ('body',),
        }),
        ('Publication', {
            'fields': ('status', 'published_at', 'is_featured', 'author_name'),
            'description': (
                'A future <em>published at</em> schedules the article: it stays '
                'invisible until that moment even with status set to Published. '
                'Leave it empty and publishing stamps it now.'
            ),
        }),
        ('Featured image', {
            'fields': ('featured_image', 'featured_image_alt'),
            'description': 'The alt text describes the image to screen readers. '
                           'Leave it empty only when the image is decorative.',
        }),
        ('Taxonomy', {
            'fields': ('categories', 'tags'),
        }),
        ('SEO', {
            'classes': ('collapse',),
            'fields': ('meta_title', 'meta_description'),
            'description': 'Both fall back to the title and summary when empty.',
        }),
        ('History', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Live', boolean=False)
    def visibility(self, obj):
        """What the public can actually see right now.

        Deliberately separate from `status`: the pair "Published" + a future date
        is the one state where the status column lies about visibility.
        """
        if obj.is_live:
            return format_html('<span style="color:#0b7d7d;">&#9679; Live</span>')
        if obj.status == Article.STATUS_PUBLISHED and obj.published_at:
            if obj.published_at > timezone.now():
                return format_html('<span style="color:#b45309;">&#9679; Scheduled</span>')
        return format_html('<span style="color:#6b7280;">&#9675; Not public</span>')

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('categories', 'tags')
