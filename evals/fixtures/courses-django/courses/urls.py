from django.urls import path

from . import views

urlpatterns = [
    path("courses/<slug:slug>/", views.course_detail, name="course_detail"),
    path("courses/<slug:slug>/enroll/", views.enroll, name="enroll"),
]
