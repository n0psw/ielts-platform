
from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()
from .utils import CsrfExemptAPIView
from .firebase_config import verify_firebase_token
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from .models import ReadingTest, ReadingQuestion, AnswerKey
from .serializers import ReadingTestListSerializer, ReadingTestDetailSerializer
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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EssaySerializer(data=request.data)
        if serializer.is_valid():
            essay = serializer.save(user=request.user)

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
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
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
    queryset = ReadingTest.objects.all()
    serializer_class = ReadingTestListSerializer


class ReadingTestDetailView(RetrieveAPIView):
    queryset = ReadingTest.objects.all()
    serializer_class = ReadingTestDetailSerializer


class ReadingTestSubmitView(APIView):
    """
    Ожидает:
    {
        "answers": {
            "12": "A",
            "13": "TRUE",
            ...
        }
    }
    """
    def post(self, request, pk):
        try:
            test = ReadingTest.objects.get(pk=pk)
        except ReadingTest.DoesNotExist:
            return Response({"error": "Test not found"}, status=404)

        answers = request.data.get("answers", {})
        total = 0
        correct = 0

        for q in test.questions.all():
            total += 1
            user_answer = answers.get(str(q.id), "").strip().upper()
            try:
                correct_answer = AnswerKey.objects.get(question=q).correct_answer.strip().upper()
                if user_answer == correct_answer:
                    correct += 1
            except AnswerKey.DoesNotExist:
                continue

        score = round((correct / total) * 40)
        band_score = self.convert_to_band(score)

        return Response({
            "total_questions": total,
            "correct_answers": correct,
            "raw_score": score,
            "band_score": band_score
        })

    def convert_to_band(self, raw_score):
        if raw_score >= 39: return 9.0
        if raw_score >= 37: return 8.5
        if raw_score >= 35: return 8.0
        if raw_score >= 33: return 7.5
        if raw_score >= 30: return 7.0
        if raw_score >= 27: return 6.5
        if raw_score >= 23: return 6.0
        if raw_score >= 19: return 5.5
        if raw_score >= 15: return 5.0
        if raw_score >= 12: return 4.5
        return 4.0

class StartWritingSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session = WritingTestSession.objects.create(user=request.user)
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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_id = request.data.get("session_id")
        task_type = request.data.get("task_type")
        submitted_text = request.data.get("submitted_text")
        question_text = request.data.get("question_text")

        if not all([session_id, task_type, submitted_text, question_text]):
            return Response({'error': 'Missing data'}, status=400)

        session = WritingTestSession.objects.get(id=session_id, user=request.user)

        existing = Essay.objects.filter(user=request.user, test_session=session, task_type=task_type).first()
        if existing:
            return Response({'error': f'{task_type} already submitted'}, status=400)

        Essay.objects.create(
            user=request.user,
            task_type=task_type,
            submitted_text=submitted_text,
            question_text=question_text,
            test_session=session
        )
        return Response({'message': f'{task_type} saved'})


class FinishWritingSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_id = request.data.get("session_id")
        session = WritingTestSession.objects.get(id=session_id, user=request.user)
        essays = session.essay_set.all()

        if essays.count() < 2:
            return Response({'error': 'Both Task 1 and Task 2 are required'}, status=400)

        for essay in essays:
            prompt = f"""
You are an IELTS examiner. Evaluate the following essay using 4 IELTS criteria (0–9):
1. Task Response
2. Coherence and Cohesion
3. Lexical Resource
4. Grammatical Range and Accuracy

Return each criterion in the format:
Task Response: 8.5
...

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

        session.completed = True
        session.band_score = round_ielts_band(
            sum(e.overall_band for e in essays) / essays.count()
        )
        session.save()

        return Response({'message': 'AI feedback saved for both tasks'})


class WritingPromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = WritingPrompt
        fields = ['id', 'task_type', 'prompt_text', 'created_at', 'image', 'is_active']



class WritingPromptViewSet(viewsets.ModelViewSet):
    queryset = WritingPrompt.objects.all().order_by('-created_at')
    serializer_class = WritingPromptSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    @action(detail=False, methods=['get'], url_path='active', permission_classes=[AllowAny])
    def get_active_prompt(self, request):
        task_type = request.query_params.get('task_type')
        if not task_type:
            return Response({"error": "task_type required"}, status=400)

        prompt = WritingPrompt.objects.filter(task_type=task_type, is_active=True).first()
        if not prompt:
            return Response({"error": "No active prompt found"}, status=404)
        return Response(WritingPromptSerializer(prompt).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        updated_prompt = serializer.save()

        if updated_prompt.is_active:
            WritingPrompt.objects.filter(
                task_type=updated_prompt.task_type,
                is_active=True
            ).exclude(pk=updated_prompt.pk).update(is_active=False)

        return Response(WritingPromptSerializer(updated_prompt).data)



