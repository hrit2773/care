import datetime

from dateutil.parser import parse
from django.db import transaction
from django.utils import timezone
from pydantic import UUID4, BaseModel
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from care.emr.api.viewsets.base import (
    EMRBaseViewSet,
    EMRRetrieveMixin,
)
from care.emr.models import TokenBooking
from care.emr.models.scheduling.booking import TokenSlot
from care.emr.models.scheduling.schedule import Availability, SchedulableResource
from care.emr.resources.scheduling.schedule.spec import (
    SlotTypeOptions,
)
from care.emr.resources.scheduling.slot.spec import (
    TokenBookingRetrieveSpec,
    TokenSlotBaseSpec,
)
from care.facility.models import PatientRegistration
from care.users.models import User
from care.utils.lock import Lock


class SlotsForDayRequestSpec(BaseModel):
    resource: UUID4
    resource_type: str = "user"
    day: datetime.date


class AppointmentBookingSpec(BaseModel):
    patient: UUID4
    reason_for_visit: str


def convert_availability_to_slots(availabilities):
    slots = {}
    for availability in availabilities:
        start_time = parse(availability["availability"]["start_time"])
        end_time = parse(availability["availability"]["end_time"])
        slot_size_in_minutes = availability["slot_size_in_minutes"]
        availability_id = availability["availability_id"]
        current_time = start_time
        i = 0
        while current_time < end_time:
            i += 1
            if i == 30:  # noqa PLR2004
                # Failsafe to prevent infinite loop
                break
            slots[
                f"{current_time.time()}-{(current_time + datetime.timedelta(minutes=slot_size_in_minutes)).time()}"
            ] = {
                "start_time": current_time.time(),
                "end_time": (
                    current_time + datetime.timedelta(minutes=slot_size_in_minutes)
                ).time(),
                "availability_id": availability_id,
            }

            current_time += datetime.timedelta(minutes=slot_size_in_minutes)
    return slots


def lock_create_appointment(token_slot, patient, created_by, reason_for_visit):
    with Lock(f"booking:resource:{token_slot.resource.id}"), transaction.atomic():
        if token_slot.allocated >= token_slot.availability.tokens_per_slot:
            raise ValidationError("Slot is already full")
        token_slot.allocated += 1
        token_slot.save()
        return TokenBooking.objects.create(
            token_slot=token_slot,
            patient=patient,
            booked_by=created_by,
            reason_for_visit=reason_for_visit,
            status="booked",
        )


class SlotViewSet(EMRRetrieveMixin, EMRBaseViewSet):
    database_model = TokenSlot
    pydantic_read_model = TokenSlotBaseSpec
    pydantic_retrieve_model = TokenBookingRetrieveSpec

    @action(detail=False, methods=["POST"])
    def get_slots_for_day(self, request, *args, **kwargs):
        return self.get_slots_for_day_handler(
            self.kwargs["facility_external_id"], request.data
        )

    @classmethod
    def get_slots_for_day_handler(cls, facility_external_id, request_data):
        facility = facility_external_id
        request_data = SlotsForDayRequestSpec(**request_data)
        user = User.objects.filter(external_id=request_data.resource).first()
        if not user:
            raise ValidationError("Resource does not exist")
        schedulable_resource_obj = SchedulableResource.objects.filter(
            facility__external_id=facility,
            resource_id=user.id,
            resource_type=request_data.resource_type,
        ).first()
        if not schedulable_resource_obj:
            raise ValidationError("Resource is not schedulable")
        # Find all relevant schedules
        availabilities = Availability.objects.filter(
            slot_type=SlotTypeOptions.appointment.value,
            schedule__valid_from__lte=request_data.day,
            schedule__valid_to__gte=request_data.day,
            schedule__resource=schedulable_resource_obj,
        )
        # Fetch all availabilities for that day of week
        calculated_dow_availabilities = []
        for schedule_availability in availabilities:
            for day_availability in schedule_availability.availability:
                if day_availability["day_of_week"] == request_data.day.weekday():
                    calculated_dow_availabilities.append(
                        {
                            "availability": day_availability,
                            "slot_size_in_minutes": schedule_availability.slot_size_in_minutes,
                            "availability_id": schedule_availability.id,
                        }
                    )
        # Remove anything that has an availability exception
        # Generate all slots already created for that day
        slots = convert_availability_to_slots(calculated_dow_availabilities)
        # Fetch all existing slots in that day
        created_slots = TokenSlot.objects.filter(
            start_datetime__date=request_data.day,
            end_datetime__date=request_data.day,
            resource=schedulable_resource_obj,
        )
        for slot in created_slots:
            slot_key = f"{slot.start_datetime.time()}-{slot.end_datetime.time()}"
            if (
                slot_key in slots
                and slots[slot_key]["availability_id"] == slot.availability.id
            ):
                slots.pop(slot_key)

        # Create everything else
        for _slot in slots:
            slot = slots[_slot]
            TokenSlot.objects.create(
                resource=schedulable_resource_obj,
                start_datetime=datetime.datetime.combine(
                    request_data.day, slot["start_time"], tzinfo=timezone.now().tzinfo
                ),
                end_datetime=datetime.datetime.combine(
                    request_data.day, slot["end_time"], tzinfo=timezone.now().tzinfo
                ),
                availability_id=slot["availability_id"],
            )
        # Compare and figure out what needs to be created
        return Response(
            {
                "results": [
                    TokenSlotBaseSpec.serialize(slot).model_dump(exclude=["meta"])
                    for slot in TokenSlot.objects.filter(
                        start_datetime__date=request_data.day,
                        end_datetime__date=request_data.day,
                        resource=schedulable_resource_obj,
                    ).select_related("availability")
                ]
            }
        )
        # Find all existing Slot objects for that period
        # Get list of all slots, create if missed
        # Return slots

    @classmethod
    def create_appointment_handler(cls, obj, request_data, user):
        request_data = AppointmentBookingSpec(**request_data)
        patient = PatientRegistration.objects.filter(
            external_id=request_data.patient
        ).first()
        if not patient:
            raise ValidationError({"Patient not found"})
        appointment = lock_create_appointment(
            obj, patient, user, request_data.reason_for_visit
        )
        return Response(
            TokenBookingRetrieveSpec.serialize(appointment).model_dump(exclude=["meta"])
        )

    @action(detail=True, methods=["POST"])
    def create_appointment(self, request, *args, **kwargs):
        return self.create_appointment_handler(
            self.get_object(), request.data, request.user
        )
