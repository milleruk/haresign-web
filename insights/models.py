"""Haresign Insights — the public editorial content this repository owns.

Deliberately small. An `Article` with a light taxonomy of categories and tags is
what a publishing workflow of this size needs; anything more elaborate would be
a CMS nobody asked for.

Two decisions are load-bearing:

**Bodies are HTML authored in TinyMCE, not Markdown.** The monolith's blog stores
TinyMCE HTML, and the whole point of matching it is that legacy articles can be
imported later byte-for-byte rather than rewritten by hand.

**"Published" is a question about time, not just a flag.** `status='published'`
with a `published_at` in the future is scheduled, not live. Every public query
goes through `Article.objects.live()` so no view can get that wrong by writing
its own filter and forgetting the clock.
"""
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from tinymce.models import HTMLField


class Category(models.Model):
    """A broad section — research, commentary, updates."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:120]
        super().save(*args, **kwargs)


class Tag(models.Model):
    """A free-form label. The legacy blog has tags and no categories, so this is
    the model an import maps onto directly."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:120]
        super().save(*args, **kwargs)


class ArticleQuerySet(models.QuerySet):
    def live(self):
        """Articles the public may see: published, and published *by now*.

        The single definition of visibility. Drafts, archived articles and
        anything scheduled for the future are excluded here rather than in each
        view, because "published" and "visible" are different questions and a
        view that conflates them leaks unpublished work.
        """
        return self.filter(
            status=Article.STATUS_PUBLISHED,
            published_at__isnull=False,
            published_at__lte=timezone.now(),
        )


class Article(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=255, unique=True,
        help_text='Used in the URL: /insights/<slug>/. Keep it stable once '
                  'published — changing it breaks existing links.',
    )
    kicker = models.CharField(
        max_length=120, blank=True,
        help_text='Short line above the headline, e.g. "Workforce". Optional.',
    )
    summary = models.TextField(
        help_text='One or two sentences. Shown on the index, on cards, and used '
                  'as the meta description when none is set.',
    )
    body = HTMLField(help_text='The article. Authored in TinyMCE and stored as HTML.')

    author_name = models.CharField(max_length=150, default='Haresign')

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
    )
    published_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text='When this goes live. A future date schedules it: the article '
                  'stays invisible until then, even when status is Published.',
    )
    is_featured = models.BooleanField(
        default=False,
        help_text='Leads the Insights index and the homepage. The most recent '
                  'featured article wins if several are ticked.',
    )

    featured_image = models.ImageField(upload_to='insights/%Y/%m/', blank=True)
    featured_image_alt = models.CharField(
        max_length=255, blank=True,
        help_text='Describes the image for screen readers. Leave empty only if '
                  'the image is purely decorative.',
    )

    meta_title = models.CharField(
        max_length=255, blank=True, help_text='Falls back to the title.')
    meta_description = models.TextField(
        blank=True, help_text='Falls back to the summary.')

    categories = models.ManyToManyField(Category, blank=True, related_name='articles')
    tags = models.ManyToManyField(Tag, blank=True, related_name='articles')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at', '-created_at']
        indexes = [models.Index(fields=['status', 'published_at'])]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('insights:detail', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:255]
        # Publishing without a date would otherwise mean "published at no time",
        # which live() reads as not visible — surprising rather than helpful.
        if self.status == self.STATUS_PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def is_live(self):
        return (
            self.status == self.STATUS_PUBLISHED
            and self.published_at is not None
            and self.published_at <= timezone.now()
        )

    @property
    def seo_title(self):
        return self.meta_title or self.title

    @property
    def seo_description(self):
        return self.meta_description or self.summary
