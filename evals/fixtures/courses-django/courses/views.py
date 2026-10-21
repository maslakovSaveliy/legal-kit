import uuid

from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from yookassa import Configuration, Payment

from .forms import EnrollForm
from .models import Course

Configuration.configure(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)


def course_detail(request, slug):
    course = get_object_or_404(Course, slug=slug)
    return render(request, "courses/detail.html", {"course": course})


def enroll(request, slug):
    course = get_object_or_404(Course, slug=slug)
    form = EnrollForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        enrollment = form.save(commit=False)
        enrollment.course = course
        enrollment.save()
        payment = Payment.create(
            {
                "amount": {"value": f"{course.price_rub}.00", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": request.build_absolute_uri("/")},
                "capture": True,
                "description": f"Курс «{course.title}»",
                "receipt": {
                    "customer": {"email": enrollment.email, "phone": enrollment.phone},
                    "items": [
                        {
                            "description": course.title,
                            "quantity": "1",
                            "amount": {"value": f"{course.price_rub}.00", "currency": "RUB"},
                            "vat_code": 1,
                        }
                    ],
                },
            },
            uuid.uuid4(),
        )
        enrollment.payment_id = payment.id
        enrollment.save(update_fields=["payment_id"])
        return redirect(payment.confirmation.confirmation_url)
    return render(request, "courses/enroll.html", {"course": course, "form": form})
