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
    is_active = models.BooleanField(default=False)

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
    image = models.ImageField(upload_to="reading_images/", null=True, blank=True)

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


class ReadingPassage(models.Model):
    test = models.OneToOneField(ReadingTest, on_delete=models.CASCADE, related_name='passage')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Passage for {self.test.title}"


class ReadingTestSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    test = models.ForeignKey(ReadingTest, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_taken = models.IntegerField(null=True, blank=True)  # in seconds
    band_score = models.FloatField(null=True, blank=True)
    raw_score = models.IntegerField(null=True, blank=True)
    answers = models.JSONField(default=dict)  # Store user's answers
    completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Reading Test Session #{self.id} - {self.user.student_id}"

    def calculate_score(self):
        total = self.test.questions.count()
        correct = 0
        for q in self.test.questions.all():
            user_answer = self.answers.get(str(q.id), "").strip().upper()
            try:
                correct_answer = AnswerKey.objects.get(question=q).correct_answer.strip().upper()
                if user_answer == correct_answer:
                    correct += 1
            except AnswerKey.DoesNotExist:
                continue
        
        self.raw_score = round((correct / total) * 40)
        self.band_score = self.convert_to_band(self.raw_score)
        self.save()

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


