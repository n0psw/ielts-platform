from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    FirebaseLoginView,
    EssaySubmissionView,
    EssayListView,
    EssayDetailView,
    ReadingTestListView,
    ReadingTestDetailView,
    StartWritingSessionView,
    SubmitTaskView,
    FinishWritingSessionView,
    WritingPromptViewSet,
    AdminEssayListView,
    StartReadingTestView,
    SubmitReadingTestView,
    ReadingTestSessionListView,
    ReadingTestSessionDetailView,
    ReadingTestCreateView,
    ActivateReadingTestView,
    ReadingTestUpdateDeleteView,
    ReadingQuestionUpdateDeleteView,
)

router = DefaultRouter()
router.register(r'prompts', WritingPromptViewSet, basename='prompt')

urlpatterns = router.urls + [
    path('login/', FirebaseLoginView.as_view(), name='firebase-login'),
    path('essay/', EssaySubmissionView.as_view(), name='essay-submit'),
    path('essays/', EssayListView.as_view(), name='essay-list'),
    path('essays/<int:pk>/', EssayDetailView.as_view(), name='essay-detail'),
    path('reading/tests/', ReadingTestListView.as_view(), name='reading-test-list'),
    path('reading/tests/create/', ReadingTestCreateView.as_view(), name='reading-test-create'),
    path('reading/tests/<int:pk>/', ReadingTestDetailView.as_view(), name='reading-test-detail'),
    path('reading/tests/<int:pk>/start/', StartReadingTestView.as_view(), name='reading-test-start'),
    path('reading/tests/<int:pk>/activate/', ActivateReadingTestView.as_view(), name='reading-test-activate'),
    path('reading/tests/<int:pk>/update/', ReadingTestUpdateDeleteView.as_view(), name='reading-test-update-delete'),
    path('reading/sessions/<int:session_id>/submit/', SubmitReadingTestView.as_view(), name='reading-test-submit'),
    path('reading/sessions/', ReadingTestSessionListView.as_view(), name='reading-session-list'),
    path('reading/sessions/<int:pk>/', ReadingTestSessionDetailView.as_view(), name='reading-session-detail'),
    path('start-writing-session/', StartWritingSessionView.as_view(), name='start-writing-session'),
    path('submit-task/', SubmitTaskView.as_view(), name='submit-task'),
    path('finish-writing-session/', FinishWritingSessionView.as_view(), name='finish-writing-session'),
    path('admin/essays/', AdminEssayListView.as_view(), name='admin-essays'),
    path('reading/questions/<int:pk>/', ReadingQuestionUpdateDeleteView.as_view(), name='reading-question-update-delete'),
]
