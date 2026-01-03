from rest_framework.routers import DefaultRouter
from .views import VideoGenerationViewSet

router = DefaultRouter()
router.register('video', VideoGenerationViewSet, basename='video')

urlpatterns = router.urls
