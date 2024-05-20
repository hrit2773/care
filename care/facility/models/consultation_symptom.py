from django.db import models

from care.facility.models.mixins.permissions.patient import (
    ConsultationRelatedPermissionMixin,
)
from care.facility.models.patient_consultation import PatientConsultation
from care.utils.models.base import BaseModel


class Symptom(models.IntegerChoices):
    OTHERS = 9
    FEVER = 2
    SORE_THROAT = 3
    COUGH = 4
    BREATHLESSNESS = 5
    MYALGIA = 6
    ABDOMINAL_DISCOMFORT = 7
    VOMITING = 8
    SPUTUM = 11
    NAUSEA = 12
    CHEST_PAIN = 13
    HEMOPTYSIS = 14
    NASAL_DISCHARGE = 15
    BODY_ACHE = 16
    DIARRHOEA = 17
    PAIN = 18
    PEDAL_EDEMA = 19
    WOUND = 20
    CONSTIPATION = 21
    HEADACHE = 22
    BLEEDING = 23
    DIZZINESS = 24
    CHILLS = 25
    GENERAL_WEAKNESS = 26
    IRRITABILITY = 27
    CONFUSION = 28
    ABDOMINAL_PAIN = 29
    JOINT_PAIN = 30
    REDNESS_OF_EYES = 31
    ANOREXIA = 32
    NEW_LOSS_OF_TASTE = 33
    NEW_LOSS_OF_SMELL = 34


class ConsultationSymptom(BaseModel, ConsultationRelatedPermissionMixin):
    symptom = models.SmallIntegerField(choices=Symptom.choices, null=False, blank=False)
    other_symptom = models.CharField(default="", blank=True, null=False)
    onset_date = models.DateTimeField(null=True, blank=True)
    cure_date = models.DateTimeField(null=True, blank=True)
    consultation = models.ForeignKey(
        PatientConsultation,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="symptoms",
    )
    created_by = models.ForeignKey(
        "users.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        "users.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    def save(self, *args, **kwargs):
        if self.other_symptom and self.symptom != Symptom.OTHERS:
            raise ValueError("Other Symptom should be empty when Symptom is not OTHERS")

        super().save(*args, **kwargs)
