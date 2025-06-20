from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()
from .utils import CsrfExemptAPIView
from .firebase_config import verify_firebase_token
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView, RetrieveUpdateDestroyAPIView
from .models import ReadingTest, ReadingQuestion, AnswerKey, ReadingTestSession, AnswerOption, ReadingPassage
from .serializers import (
    ReadingTestListSerializer, ReadingTestDetailSerializer, EssaySerializer, WritingPromptSerializer,
    ReadingTestSessionSerializer, ReadingPassageSerializer, ReadingTestCreateSerializer, ReadingQuestionSerializer, ReadingQuestionUpdateSerializer, ReadingTestSessionResultSerializer
)
from .models import WritingTestSession
from rest_framework import serializers
from rest_framework import viewsets
from .models import WritingPrompt
from .serializers import WritingPromptSerializer
from rest_framework.generics import ListAPIView
from .models import Essay, User
from .serializers import EssaySerializer
from .permissions import IsAdmin
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
import re
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class FirebaseLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        id_token = request.data.get('idToken')
        decoded_token = verify_firebase_token(id_token)
        if not decoded_token:
            return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

        uid = decoded_token['uid']
        role = request.data.get('role')
        student_id = request.data.get('student_id')

        user, created = User.objects.get_or_create(
            uid=uid,
            defaults={'role': role, 'student_id': student_id}
        )
        if not user.student_id and student_id:
            user.student_id = student_id
            user.save()

        return Response({
            'message': 'Login successful',
            'uid': uid,
            'role': user.role,
            'student_id': user.student_id
        })


class EssaySubmissionView(CsrfExemptAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Проверяем аутентификацию через Firebase token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Authentication required'}, status=401)
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Response({'error': 'Invalid token'}, status=401)
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=401)

        serializer = EssaySerializer(data=request.data)
        if serializer.is_valid():
            essay = serializer.save(user=user)

            prompt = f"""
                        You are an IELTS examiner. Evaluate the following essay using 4 IELTS Writing criteria.  
                        Score each from 0 to 9 and return the result in plain text format like:
                        
                        Task Response: 8.5
                        Coherence and Cohesion: 8
                        Lexical Resource: 8
                        Grammatical Range and Accuracy: 9
                        
                        Feedback: <full feedback here>
                        
                        Essay:
                        {essay.submitted_text}
                        """

            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an IELTS writing examiner."},
                    {"role": "user", "content": prompt}
                ]
            )

            content = response.choices[0].message.content.strip()

            def extract_score(label):
                match = re.search(rf"{label}[:：]?\s*(\d+(\.\d+)?)", content, re.IGNORECASE)
                return float(match.group(1)) if match else 0

            def round_ielts_band(score):
                decimal = score - int(score)
                if decimal < 0.25:
                    return float(int(score))
                elif decimal < 0.75:
                    return float(int(score)) + 0.5
                else:
                    return float(int(score)) + 1.0

            essay.score_task = extract_score("Task Response")
            essay.score_coherence = extract_score("Coherence and Cohesion")
            essay.score_lexical = extract_score("Lexical Resource")
            essay.score_grammar = extract_score("Grammatical Range and Accuracy")
            essay.overall_band = round_ielts_band((
                essay.score_task + essay.score_coherence + essay.score_lexical + essay.score_grammar
            ) / 4)
            essay.feedback = content
            essay.save()

            return Response(EssaySerializer(essay).data)

        return Response(serializer.errors, status=400)

class AdminEssayListView(ListAPIView):
    serializer_class = EssaySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Проверяем аутентификацию через Firebase token
        auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Essay.objects.none()
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Essay.objects.none()
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            if user.role != 'admin':
                return Essay.objects.none()
        except User.DoesNotExist:
            return Essay.objects.none()

        queryset = Essay.objects.select_related('user').order_by('-submitted_at')
        student_id = self.request.query_params.get('student_id')
        if student_id:
            queryset = queryset.filter(user__student_id=student_id)

        return queryset


class EssayListView(ListAPIView):
    serializer_class = EssaySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Essay.objects.none()

        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Essay.objects.none()

        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            session_id = self.request.query_params.get("session_id")
            queryset = Essay.objects.filter(user=user)
            if session_id:
                queryset = queryset.filter(test_session_id=session_id)
            return queryset.order_by('-submitted_at')
        except User.DoesNotExist:
            return Essay.objects.none()


class EssayDetailView(RetrieveAPIView):
    serializer_class = EssaySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Essay.objects.none()

        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Essay.objects.none()

        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            session_id = self.request.GET.get("session_id")
            if session_id:
                return Essay.objects.filter(user=user, test_session_id=session_id).order_by('task_type')
            return Essay.objects.filter(user=user).order_by('-submitted_at')
        except User.DoesNotExist:
            return Essay.objects.none()

class ReadingTestListView(ListAPIView):
    serializer_class = ReadingTestListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Проверяем аутентификацию через Firebase token
        auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            id_token = auth_header.split(' ')[1]
            decoded = verify_firebase_token(id_token)
            if decoded:
                uid = decoded['uid']
                try:
                    user = User.objects.get(uid=uid)
                    if user.role == 'admin':
                        return ReadingTest.objects.all()
                except User.DoesNotExist:
                    pass
        return ReadingTest.objects.filter(is_active=True)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

class ReadingTestDetailView(RetrieveAPIView):
    serializer_class = ReadingTestDetailSerializer
    permission_classes = [AllowAny]
    queryset = ReadingTest.objects.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

class StartReadingTestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        # Проверяем аутентификацию через Firebase token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Authentication required'}, status=401)
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Response({'error': 'Invalid token'}, status=401)
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=401)

        try:
            test = ReadingTest.objects.get(pk=pk)
        except ReadingTest.DoesNotExist:
            return Response({"error": "Test not found"}, status=404)

        # Check if user has an incomplete session
        existing_session = ReadingTestSession.objects.filter(
            user=user,
            test=test,
            completed=False
        ).first()

        from .serializers import ReadingTestDetailSerializer
        test_data = ReadingTestDetailSerializer(test).data

        if existing_session:
            return Response({
                "session_id": existing_session.id,
                "test": test_data,
                "message": "Resuming existing session"
            })

        # Create new session
        session = ReadingTestSession.objects.create(
            user=user,
            test=test
        )

        return Response({
            "session_id": session.id,
            "test": test_data,
            "message": "New session started"
        })

class SubmitReadingTestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, session_id):
        # Проверяем аутентификацию через Firebase token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Authentication required'}, status=401)
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Response({'error': 'Invalid token'}, status=401)
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=401)

        try:
            session = ReadingTestSession.objects.get(id=session_id, user=user)
        except ReadingTestSession.DoesNotExist:
            # Если сессия не найдена, создаем новую (например, если студент перезагрузил страницу)
            test_id = request.data.get("test_id")
            if not test_id:
                return Response({"error": "Test ID not provided"}, status=400)
            test = ReadingTest.objects.get(pk=test_id)
            session = ReadingTestSession.objects.create(user=user, test=test, completed=False)
        
        # Обновляем сессию (всегда)
        session.answers = request.data.get("answers", {})
        session.completed = True
        session.completed_at = timezone.now()
        session.time_taken = request.data.get("time_taken")
        session.calculate_score()
        session.save()
        return Response({ "message": "Test submitted successfully", "band_score": session.band_score, "raw_score": session.raw_score, "time_taken": session.time_taken })

class ReadingTestSessionListView(ListAPIView):
    serializer_class = ReadingTestSessionSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Проверяем аутентификацию через Firebase token
        auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return ReadingTestSession.objects.none()
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return ReadingTestSession.objects.none()
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            return ReadingTestSession.objects.filter(
                user=user,
                completed=True
            ).select_related('test')
        except User.DoesNotExist:
            return ReadingTestSession.objects.none()

class ReadingTestSessionDetailView(RetrieveAPIView):
    serializer_class = ReadingTestSessionResultSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Проверяем аутентификацию через Firebase token
        auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return ReadingTestSession.objects.none()
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return ReadingTestSession.objects.none()
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            return ReadingTestSession.objects.filter(
                user=user
            ).select_related('test')
        except User.DoesNotExist:
            return ReadingTestSession.objects.none()

class StartWritingSessionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Проверяем аутентификацию через Firebase token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Authentication required'}, status=401)
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Response({'error': 'Invalid token'}, status=401)
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=401)

        session = WritingTestSession.objects.create(user=user)
        task1_prompt = WritingPrompt.objects.filter(task_type="task1").order_by("?").first()
        task2_prompt = WritingPrompt.objects.filter(task_type="task2").order_by("?").first()

        return Response({
            'session_id': session.id,
            'task1_prompt_id': task1_prompt.id if task1_prompt else None,
            'task2_prompt_id': task2_prompt.id if task2_prompt else None,
            'task1_text': task1_prompt.prompt_text if task1_prompt else "No Task 1 available",
            'task2_text': task2_prompt.prompt_text if task2_prompt else "No Task 2 available"
        })


class SubmitTaskView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Проверяем аутентификацию через Firebase token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Authentication required'}, status=401)
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Response({'error': 'Invalid token'}, status=401)
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=401)

        serializer = EssaySerializer(data=request.data)
        if serializer.is_valid():
            essay = serializer.save(user=user)

            prompt = f"""
                        You are an IELTS examiner. Evaluate the following essay using 4 IELTS Writing criteria.  
                        Score each from 0 to 9 and return the result in plain text format like:
                        
                        Task Response: 8.5
                        Coherence and Cohesion: 8
                        Lexical Resource: 8
                        Grammatical Range and Accuracy: 9
                        
                        Feedback: <full feedback here>
                        
                        Essay:
                        {essay.submitted_text}
                        """

            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an IELTS writing examiner."},
                    {"role": "user", "content": prompt}
                ]
            )

            content = response.choices[0].message.content.strip()

            def extract_score(label):
                match = re.search(rf"{label}[:：]?\s*(\d+(\.\d+)?)", content, re.IGNORECASE)
                return float(match.group(1)) if match else 0

            def round_ielts_band(score):
                decimal = score - int(score)
                if decimal < 0.25:
                    return float(int(score))
                elif decimal < 0.75:
                    return float(int(score)) + 0.5
                else:
                    return float(int(score)) + 1.0

            essay.score_task = extract_score("Task Response")
            essay.score_coherence = extract_score("Coherence and Cohesion")
            essay.score_lexical = extract_score("Lexical Resource")
            essay.score_grammar = extract_score("Grammatical Range and Accuracy")
            essay.overall_band = round_ielts_band((
                essay.score_task + essay.score_coherence + essay.score_lexical + essay.score_grammar
            ) / 4)
            essay.feedback = content
            essay.save()

            return Response(EssaySerializer(essay).data)

        return Response(serializer.errors, status=400)


class FinishWritingSessionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Проверяем аутентификацию через Firebase token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Authentication required'}, status=401)
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Response({'error': 'Invalid token'}, status=401)
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=401)

        session_id = request.data.get("session_id")
        if not session_id:
            return Response({'error': 'Session ID required'}, status=400)

        try:
            session = WritingTestSession.objects.get(id=session_id, user=user)
        except WritingTestSession.DoesNotExist:
            return Response({'error': 'Session not found'}, status=404)

        essays = Essay.objects.filter(user=user, test_session=session)
        if not essays.exists():
            return Response({'error': 'No essays found for this session'}, status=400)

        # Calculate overall band score
        total_score = 0
        essay_count = 0
        
        for essay in essays:
            if essay.overall_band:
                total_score += essay.overall_band
                essay_count += 1

        if essay_count > 0:
            overall_band = total_score / essay_count
        else:
            overall_band = 0

        return Response({
            'session_id': session.id,
            'overall_band': round(overall_band, 1),
            'essays_count': essay_count,
            'message': 'Session completed successfully'
        })


class WritingPromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = WritingPrompt
        fields = ['id', 'task_type', 'prompt_text', 'created_at', 'image', 'is_active']



class WritingPromptViewSet(viewsets.ModelViewSet):
    queryset = WritingPrompt.objects.all().order_by('-created_at')
    serializer_class = WritingPromptSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Проверяем аутентификацию через Firebase token
        auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return WritingPrompt.objects.none()
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return WritingPrompt.objects.none()
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            if user.role != 'admin':
                return WritingPrompt.objects.none()
        except User.DoesNotExist:
            return WritingPrompt.objects.none()

        return WritingPrompt.objects.all().order_by('-created_at')

    @action(detail=False, methods=['get'], url_path='active', permission_classes=[AllowAny])
    def get_active_prompt(self, request):
        task_type = request.query_params.get('task_type', 'task1')
        prompt = WritingPrompt.objects.filter(task_type=task_type, is_active=True).first()
        if prompt:
            return Response(WritingPromptSerializer(prompt).data)
        return Response({'error': 'No active prompt found'}, status=404)

    def update(self, request, *args, **kwargs):
        # Проверяем аутентификацию через Firebase token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Authentication required'}, status=401)
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Response({'error': 'Invalid token'}, status=401)
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            if user.role != 'admin':
                return Response({'error': 'Admin access required'}, status=403)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=401)

        return super().update(request, *args, **kwargs)

class ReadingTestCreateView(APIView):
    permission_classes = [AllowAny]  # Временно разрешаем всем для отладки

    def post(self, request):
        # Проверяем аутентификацию через Firebase token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Authentication required'}, status=401)
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Response({'error': 'Invalid token'}, status=401)
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            if user.role != 'admin':
                return Response({'error': 'Admin access required'}, status=403)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=401)

        data = request.data.copy()
        # Парсим вопросы из JSON
        questions_json = data.get('questions')
        if questions_json:
            if isinstance(questions_json, str):
                questions = json.loads(questions_json)
            else:
                questions = questions_json
        else:
            questions = []
        
        # Подменяем image на файл из request.FILES
        for idx, q in enumerate(questions):
            image_field = f'question_image_{idx}'
            if image_field in request.FILES:
                q['image'] = request.FILES[image_field]
        
        # Собираем словарь для сериализатора
        test_data = {
            'title': data['title'],
            'description': data.get('description', ''),
            'passage': data['passage'],
            'questions': questions
        }
        
        serializer = ReadingTestCreateSerializer(data=test_data)
        if serializer.is_valid():
            test = serializer.save()
            return Response({'id': test.id, 'message': 'Test created successfully'}, status=201)
        return Response(serializer.errors, status=400)

class ActivateReadingTestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        # Проверяем аутентификацию через Firebase token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Response({'error': 'Authentication required'}, status=401)
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return Response({'error': 'Invalid token'}, status=401)
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            if user.role != 'admin':
                return Response({'error': 'Admin access required'}, status=403)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=401)

        ReadingTest.objects.all().update(is_active=False)
        test = ReadingTest.objects.get(pk=pk)
        test.is_active = True
        test.save()
        return Response({'message': 'Test activated', 'id': test.id})

class ReadingTestUpdateDeleteView(RetrieveUpdateDestroyAPIView):
    queryset = ReadingTest.objects.all()
    serializer_class = ReadingTestCreateSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Проверяем аутентификацию через Firebase token
        auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return ReadingTest.objects.none()
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return ReadingTest.objects.none()
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            if user.role != 'admin':
                return ReadingTest.objects.none()
        except User.DoesNotExist:
            return ReadingTest.objects.none()

        return ReadingTest.objects.all()

class ReadingQuestionUpdateDeleteView(RetrieveUpdateDestroyAPIView):
    queryset = ReadingQuestion.objects.all()
    serializer_class = ReadingQuestionUpdateSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Проверяем аутентификацию через Firebase token
        auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return ReadingQuestion.objects.none()
        
        id_token = auth_header.split(' ')[1]
        decoded = verify_firebase_token(id_token)
        if not decoded:
            return ReadingQuestion.objects.none()
        
        uid = decoded['uid']
        try:
            user = User.objects.get(uid=uid)
            if user.role != 'admin':
                return ReadingQuestion.objects.none()
        except User.DoesNotExist:
            return ReadingQuestion.objects.none()

        return ReadingQuestion.objects.all()



