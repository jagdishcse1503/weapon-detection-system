from django.db import models
from django.contrib.auth.models import User

class EmailOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)

class DetectionRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_file = models.FileField(upload_to='uploads/')
    output_file = models.FileField(upload_to='outputs/', null=True, blank=True)
    file_type = models.CharField(max_length=10, choices=[('image', 'Image'), ('video', 'Video')])
    detected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.file_type} - {self.detected_at.strftime('%Y-%m-%d %H:%M')}"