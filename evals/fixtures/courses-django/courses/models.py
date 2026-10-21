from django.db import models


class Course(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    price_rub = models.PositiveIntegerField()
    hours = models.PositiveIntegerField()

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=32)
    paid = models.BooleanField(default=False)
    payment_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Certificate(models.Model):
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE)
    number = models.CharField(max_length=32, unique=True)
    issued_at = models.DateField(auto_now_add=True)
