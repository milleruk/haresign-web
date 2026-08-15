import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Subscriber',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('name', models.CharField(blank=True, max_length=150)),
                ('subscribed_at', models.DateTimeField(auto_now_add=True)),
                ('active', models.BooleanField(default=True)),
                ('unsubscribe_token', models.UUIDField(default=uuid.uuid4,
                                                       editable=False, unique=True)),
                ('source', models.CharField(blank=True, max_length=60)),
            ],
            options={
                'verbose_name': 'Newsletter subscriber',
                'verbose_name_plural': 'Newsletter subscribers',
                'ordering': ['-subscribed_at'],
            },
        ),
    ]
