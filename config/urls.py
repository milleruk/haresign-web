from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # The publishing backend. Editorial staff logins only — see settings.py on
    # why auth lives here and why it is not Haresign identity.
    path('admin/', admin.site.urls),
    path('tinymce/', include('tinymce.urls')),

    path('insights/', include('insights.urls', namespace='insights')),

    # Last: web owns '' and the catch-all-ish public routes.
    path('', include('web.urls')),
]
