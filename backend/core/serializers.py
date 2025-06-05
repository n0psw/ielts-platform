from rest_framework import serializers
from .models import ReadingTest, ReadingQuestion, AnswerOption, AnswerKey, Essay, WritingPrompt

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
    options = AnswerOptionSerializer(many=True, read_only=True)

    class Meta:
        model = ReadingQuestion
        fields = ['id', 'order', 'question_type', 'question_text', 'paragraph_ref', 'options']


class ReadingTestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingTest
        fields = ['id', 'title', 'description']


class ReadingTestDetailSerializer(serializers.ModelSerializer):
    questions = ReadingQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = ReadingTest
        fields = ['id', 'title', 'description', 'questions']

class WritingPromptSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(allow_null=True, required=False)
    class Meta:
        model = WritingPrompt
        fields = ['id', 'task_type', 'prompt_text', 'created_at', 'image', 'is_active']
