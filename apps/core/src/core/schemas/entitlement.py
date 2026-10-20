from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

# Strict: "10" or true is not a number, and infinity or NaN is no cap.
_Cap = Annotated[float, Field(ge=0, strict=True, allow_inf_nan=False)]


def naive_utc(value: datetime) -> datetime:
    """The columns hold naive UTC: an aware time is converted, a naive one is UTC already."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class OdooEntitlement(BaseModel):
    """What Odoo pushes for an organization (docs/odoo-entitlement-contract.md).

    Absent fields leave the organization as is; a cap of null means unlimited.
    """

    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    suspended: StrictBool | None = None
    on_trial: StrictBool | None = None
    total_credits: _Cap | None = None
    total_storage: _Cap | None = None
    total_projects: _Cap | None = None
    total_editors: _Cap | None = None
    total_viewers: _Cap | None = None
    extras: list[str] | None = None
    plan_renewal_date: datetime | None = None
    # Odoo-side time of this data: an older push than the applied one is stale.
    as_of: datetime | None = None
    reset_usage: StrictBool = False

    @field_validator("suspended", "on_trial")
    @classmethod
    def _flag_is_not_null(cls, value: bool | None) -> bool | None:
        if value is None:
            raise ValueError("must be true or false")
        return value

    @field_validator("total_projects", "total_editors", "total_viewers")
    @classmethod
    def _count_is_whole(cls, value: float | None) -> int | None:
        if value is None:
            return None
        if value != int(value):
            raise ValueError("must be a whole number")
        return int(value)

    @field_validator("extras", mode="before")
    @classmethod
    def _extras_are_strings(cls, value: object) -> object:
        if isinstance(value, list) and not all(isinstance(e, str) for e in value):
            raise ValueError("must be a list of strings")
        return value

    @field_validator("plan_renewal_date", "as_of", mode="before")
    @classmethod
    def _iso_string(cls, value: object) -> object:
        # No unix timestamps: pydantic would read a number as one.
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("must be an ISO 8601 datetime string")
        return value

    @field_validator("plan_renewal_date", "as_of")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return naive_utc(value) if value is not None else None

    def entitlement(self) -> dict:
        """The fields Odoo sent, for CRUDOrganization.apply_entitlement."""
        return self.model_dump(
            exclude_unset=True, exclude={"organization_id", "reset_usage"}
        )


class TrialStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    stage: Literal["expiring", "expired"]
