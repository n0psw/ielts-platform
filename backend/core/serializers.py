from rest_framework import serializers
from .models import ReadingTest, ReadingQuestion, AnswerOption, AnswerKey, Essay, WritingPrompt, ReadingPassage, ReadingTestSession, User

class EssaySerializer(serializers.ModelSerializer):
    student_id = serializers.CharField(source='user.student_id', read_only=True)
    class Meta:
        model = Essay
        fields = '__all__'
        read_only_fields = [
            'user', 'submitted_at',
            'score_task', 'score_coherence', 'score_lexical',
            'score_grammar', 'overall_band', 'feedback'
        ]
        extra_kwargs = {
            'question_text': {'required': False, 'allow_blank': True},
            'submitted_text': {'required': True},
        }

class AnswerOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerOption
        fields = ['label', 'text']


class ReadingQuestionSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    options = AnswerOptionSerializer(many=True, read_only=True)
    correct_answer = serializers.SerializerMethodField()

    class Meta:
        model = ReadingQuestion
        fields = ['id', 'order', 'question_type', 'question_text', 'paragraph_ref', 'options', 'image', 'correct_answer']

    def get_image(self, obj):
        request = self.context.get('request', None)
        if obj.image and hasattr(obj.image, 'url'):
            if request is not None:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_correct_answer(self, obj):
        try:
            return AnswerKey.objects.get(question=obj).correct_answer
        except AnswerKey.DoesNotExist:
            return None


class ReadingPassageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingPassage
        fields = ['text', 'created_at', 'updated_at']


class ReadingTestSessionSerializer(serializers.ModelSerializer):
    test_title = serializers.CharField(source='test.title', read_only=True)
    student_id = serializers.CharField(source='user.student_id', read_only=True)
    
    class Meta:
        model = ReadingTestSession
        fields = ['id', 'test', 'test_title', 'student_id', 'started_at', 'completed_at', 
                 'time_taken', 'band_score', 'raw_score', 'completed', 'answers']
        read_only_fields = ['user', 'started_at', 'completed_at', 'band_score', 'raw_score', 'completed']


class ReadingTestListSerializer(serializers.ModelSerializer):
    has_attempted = serializers.SerializerMethodField()
    is_active = serializers.BooleanField()

    class Meta:
        model = ReadingTest
        fields = ['id', 'title', 'description', 'has_attempted', 'is_active']

    def get_has_attempted(self, obj):
        request = self.context.get('request')
        if request:
            # Проверяем аутентификацию через Firebase token
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                from .firebase_config import verify_firebase_token
                
                id_token = auth_header.split(' ')[1]
                decoded = verify_firebase_token(id_token)
                if decoded:
                    uid = decoded['uid']
                    try:
                        user = User.objects.get(uid=uid)
                        return ReadingTestSession.objects.filter(
                            test=obj,
                            user=user,
                            completed=True
                        ).exists()
                    except User.DoesNotExist:
                        pass
        return False


class ReadingTestDetailSerializer(serializers.ModelSerializer):
    questions = ReadingQuestionSerializer(many=True, read_only=True)
    passage = ReadingPassageSerializer(read_only=True)
    time_limit = serializers.IntegerField(default=60)  # 60 minutes default
    is_active = serializers.BooleanField()

    class Meta:
        model = ReadingTest
        fields = ['id', 'title', 'description', 'questions', 'passage', 'time_limit', 'is_active']

class WritingPromptSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(allow_null=True, required=False)
    class Meta:
        model = WritingPrompt
        fields = ['id', 'task_type', 'prompt_text', 'created_at', 'image', 'is_active']

class AnswerOptionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerOption
        fields = ['label', 'text']

class ReadingQuestionCreateSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(allow_null=True, required=False)
    options = AnswerOptionCreateSerializer(many=True, required=False)
    correct_answer = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = ReadingQuestion
        fields = ['question_type', 'question_text', 'order', 'options', 'image', 'correct_answer']

class ReadingTestCreateSerializer(serializers.ModelSerializer):
    questions = ReadingQuestionCreateSerializer(many=True)
    passage = serializers.CharField(write_only=True)

    class Meta:
        model = ReadingTest
        fields = ['title', 'description', 'questions', 'passage']

    def create(self, validated_data):
        questions_data = validated_data.pop('questions')
        passage_text = validated_data.pop('passage')
        test = ReadingTest.objects.create(**validated_data)
        ReadingPassage.objects.create(test=test, text=passage_text)
        for q_data in questions_data:
            options_data = q_data.pop('options', [])
            image = q_data.pop('image', None)
            correct_answer = q_data.pop('correct_answer', None)
            question = ReadingQuestion.objects.create(test=test, image=image, **q_data)
            for opt_data in options_data:
                AnswerOption.objects.create(question=question, **opt_data)
            if correct_answer:
                AnswerKey.objects.create(question=question, correct_answer=correct_answer)
        return test

class ReadingQuestionUpdateSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(allow_null=True, required=False)
    options = AnswerOptionCreateSerializer(many=True, required=False)
    correct_answer = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = ReadingQuestion
        fields = ['question_type', 'question_text', 'order', 'options', 'image', 'correct_answer']

    def update(self, instance, validated_data):
        correct_answer = validated_data.pop('correct_answer', None)
        instance = super().update(instance, validated_data)
        if correct_answer is not None:
            AnswerKey.objects.update_or_create(question=instance, defaults={'correct_answer': correct_answer})
        return instance

class ReadingTestSessionResultSerializer(serializers.ModelSerializer):
    test_title = serializers.CharField(source='test.title', read_only=True)
    student_id = serializers.CharField(source='user.student_id', read_only=True)
    correct_answers = serializers.SerializerMethodField()
    total_questions = serializers.SerializerMethodField()
    question_feedback = serializers.SerializerMethodField()

    class Meta:
        model = ReadingTestSession
        fields = [
            'id', 'test', 'test_title', 'student_id', 'started_at', 'completed_at',
            'time_taken', 'band_score', 'raw_score', 'completed', 'answers',
            'correct_answers', 'total_questions', 'question_feedback'
        ]
        read_only_fields = ['user', 'started_at', 'completed_at', 'band_score', 'raw_score', 'completed']

    def get_correct_answers(self, obj):
        correct = 0
        for q in obj.test.questions.all():
            user_answer = obj.answers.get(str(q.id), '').strip().upper()
            try:
                correct_answer = AnswerKey.objects.get(question=q).correct_answer.strip().upper()
                if user_answer == correct_answer:
                    correct += 1
            except AnswerKey.DoesNotExist:
                continue
        return correct

    def get_total_questions(self, obj):
        return obj.test.questions.count()

    def get_question_feedback(self, obj):
        feedback = []
        for q in obj.test.questions.all().order_by('order'):
            user_answer = obj.answers.get(str(q.id), '').strip()
            try:
                correct_answer = AnswerKey.objects.get(question=q).correct_answer.strip()
                is_correct = user_answer.strip().upper() == correct_answer.strip().upper()
            except AnswerKey.DoesNotExist:
                correct_answer = None
                is_correct = False
            feedback.append({
                'question_order': q.order,
                'question_text': q.question_text,
                'user_answer': user_answer,
                'correct_answer': correct_answer,
                'correct': is_correct,
            })
        return feedback
