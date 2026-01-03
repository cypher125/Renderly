from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('video_generation', '0001_initial'),
    ]
    operations = [
        migrations.AddField(
            model_name='videojob',
            name='webhook_url',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='videojob',
            name='events',
            field=models.JSONField(default=list),
        ),
    ]
