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


class HasImageAltFilter(admin.SimpleListFilter):
    """Find articles whose featured image has no description.

    Not a defect list — decorative is a legitimate and usually correct answer
    here. It is a work queue for the editorial review, so that "we decided" and
    "we never looked" stop looking the same.
    """
    title = 'featured image alt text'
    parameter_name = 'has_alt'

    def lookups(self, request, model_admin):
        return [('yes', 'Described'), ('no', 'Decorative (no alt text)'),
                ('none', 'No image')]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.exclude(featured_image_alt='')
        if self.value() == 'no':
            return queryset.filter(featured_image_alt='').exclude(featured_image='')
        if self.value() == 'none':
            return queryset.filter(featured_image='')
        return queryset


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
    list_display = ['title', 'visibility', 'image_alt', 'status', 'published_at',
                    'is_featured', 'author_name']
    list_filter = ['status', 'is_featured', 'categories', 'tags', 'published_at',
                   HasImageAltFilter]
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
            'description': (
                'Leave the alt text empty when the image is <strong>decorative</strong> '
                '&mdash; which it is whenever the picture only repeats the headline '
                'printed beside it, as the imported header cards do. The page then '
                'marks it decorative explicitly, so a screen reader skips it rather '
                'than announcing an unlabelled image.<br><br>'
                'Fill it in when the image carries something the headline does not '
                '&mdash; a chart with figures in it, for instance. The '
                '<em>Image alt</em> column and the filter beside this list show which '
                'articles have one.'
            ),
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

    @admin.display(description='Image alt')
    def image_alt(self, obj):
        """Whether the featured image is described or explicitly decorative.

        Every imported article arrived without alt text, because the monolith has
        no such field and inventing 67 descriptions would have been fabrication.
        Decorative is the right answer for a header card that repeats the
        headline — but "right answer" and "nobody looked" are indistinguishable
        without this column, which is what makes the editorial review possible.
        """
        if not obj.featured_image:
            return format_html('<span style="color:#9ca3af;">&mdash;</span>')
        if obj.featured_image_alt:
            return format_html('<span style="color:#0b7d7d;">&#9679; Described</span>')
        return format_html('<span style="color:#6b7280;">&#9675; Decorative</span>')

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
