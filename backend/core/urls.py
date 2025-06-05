from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    FirebaseLoginView,
    EssaySubmissionView,
    EssayListView,
    EssayDetailView,
    ReadingTestListView,
    ReadingTestDetailView,
    ReadingTestSubmitView,
    StartWritingSessionView,
    SubmitTaskView,
    FinishWritingSessionView,
    WritingPromptViewSet,
    AdminEssayListView,
)

router = DefaultRouter()
router.register(r'prompts', WritingPromptViewSet, basename='prompt')

urlpatterns = router.urls + [
    path('login/', FirebaseLoginView.as_view(), name='firebase-login'),
    path('essay/', EssaySubmissionView.as_view(), name='essay-submit'),
    path('essays/', EssayListView.as_view(), name='essay-list'),
    path('essays/<int:pk>/', EssayDetailView.as_view(), name='essay-detail'),
    path('reading-tests/', ReadingTestListView.as_view(), name='reading-test-list'),
    path('reading-tests/<int:pk>/', ReadingTestDetailView.as_view(), name='reading-test-detail'),
    path('reading-tests/<int:pk>/submit/', ReadingTestSubmitView.as_view(), name='reading-test-submit'),
    path('start-writing-session/', StartWritingSessionView.as_view(), name='start-writing-session'),
    path('submit-task/', SubmitTaskView.as_view(), name='submit-task'),
    path('finish-writing-session/', FinishWritingSessionView.as_view(), name='finish-writing-session'),
    path('admin/essays/', AdminEssayListView.as_view(), name='admin-essays'),
]
