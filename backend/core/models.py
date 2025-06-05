from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager

class UserManager(BaseUserManager):
    def create_user(self, uid, role):
        user = self.model(uid=uid, role=role)
        user.save(using=self._db)
        return user

class User(AbstractBaseUser):
    uid = models.CharField(max_length=128, unique=True)
    role = models.CharField(max_length=20, choices=[('student', 'Student'), ('admin', 'Admin')])
    student_id = models.CharField(max_length=64, null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'uid'

class WritingTestSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    band_score = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"TestSession #{self.id} for {self.user.uid}"

class WritingPrompt(models.Model):
    task_type = models.CharField(max_length=10, choices=[('task1', 'Task 1'), ('task2', 'Task 2')])
    prompt_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to="writing_images/", null=True, blank=True)
    is_active = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        print(">>> WritingPrompt.save() called")
        if self.is_active:
            WritingPrompt.objects.filter(
                task_type=self.task_type,
                is_active=True
            ).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.task_type.upper()} - {self.prompt_text[:50]}"


class Essay(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    task_type = models.CharField(max_length=10, choices=[('task1', 'Task 1'), ('task2', 'Task 2')])
    question_text = models.TextField()
    submitted_text = models.TextField()
    score_task = models.FloatField(null=True)
    score_coherence = models.FloatField(null=True)
    score_lexical = models.FloatField(null=True)
    score_grammar = models.FloatField(null=True)
    overall_band = models.FloatField(null=True)
    feedback = models.TextField(null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    test_session = models.ForeignKey(WritingTestSession, on_delete=models.CASCADE, null=True, blank=True)
    prompt = models.ForeignKey(WritingPrompt, null=True, blank=True, on_delete=models.SET_NULL)


class ReadingTest(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class ReadingQuestion(models.Model):
    QUESTION_TYPES = [
        ('MULTIPLE_CHOICE', 'Multiple Choice'),
        ('TRUE_FALSE_NOT_GIVEN', 'True / False / Not Given'),
        ('MATCHING_HEADINGS', 'Matching Headings'),
    ]
    test = models.ForeignKey(ReadingTest, related_name='questions', on_delete=models.CASCADE)
    question_type = models.CharField(max_length=50, choices=QUESTION_TYPES)
    question_text = models.TextField()
    paragraph_ref = models.TextField(blank=True)
    order = models.PositiveIntegerField()

    def __str__(self):
        return f"Q{self.order} ({self.get_question_type_display()})"


class AnswerOption(models.Model):
    question = models.ForeignKey(ReadingQuestion, related_name='options', on_delete=models.CASCADE)
    text = models.CharField(max_length=255)
    label = models.CharField(max_length=5)

    def __str__(self):
        return f"{self.label}: {self.text}"


class AnswerKey(models.Model):
    question = models.OneToOneField(ReadingQuestion, on_delete=models.CASCADE)
    correct_answer = models.CharField(max_length=255)

    def __str__(self):
        return f"Answer to Q{self.question.id}: {self.correct_answer}"


