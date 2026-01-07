from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("video_generation", "0003_remove_videojob_events_remove_videojob_webhook_url"),
    ]

    operations = [
        migrations.AlterField(
            model_name="videojob",
            name="final_video_url",
            field=models.URLField(blank=True, max_length=2048),
        ),
    ]

