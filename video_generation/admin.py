from django.contrib import admin
from .models import VideoJob

@admin.register(VideoJob)
class VideoJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'product_title', 'status', 'progress', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('product_title', 'id', 'user__username')
