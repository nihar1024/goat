"""What a bundle states about where its data came from.

A **bundle** is the unit a user acquires — a GTFS feed, an Overture extract —
so licence and distribution describe the whole acquisition. It is stored as a
single JSONB `dataset_metadata` column, because an importer produces a sparse
dict and a source that starts stating one more thing about itself should not
need a migration.

A **layer** has no equivalent. A user's uploaded dataset is described by its
name, description and tags; a promoted catalog layer carries the catalog's own
record verbatim in `other_properties.catalog_item`, in the catalog's
vocabulary. Nothing translates between the two — a licence identifier like
`DL-DE-BY-2.0` is more precise than any enum we would map it into.

`dataset_metadata`, not `metadata`: SQLAlchemy's Declarative API reserves
`metadata` as an attribute name (it is the MetaData registry), so a model field
cannot be called that.
"""

from enum import Enum

import pycountry
from pydantic import BaseModel, EmailStr, Field, field_validator


class DataLicense(str, Enum):
    """The licences a bundle owner can pick from.

    A closed list because this is a dropdown someone fills in by hand. It says
    nothing about what a catalog dataset is published under — a promoted catalog
    layer keeps the provider's own identifier (`DL-DE-BY-2.0`) in
    `other_properties.catalog_item`, untranslated.
    """

    DDN2 = "DDN2"
    DDZ2 = "DDZ2"
    CC_BY = "CC_BY"
    CC_BY_SA = "CC_BY_SA"
    CC_BY_ND = "CC_BY_ND"
    CC_BY_NC = "CC_BY_NC"
    CC_BY_NC_SA = "CC_BY_NC_SA"
    CC_BY_NC_ND = "CC_BY_NC_ND"
    CC_ZERO = "CC_ZERO"
    ODC_BY = "ODC_BY"
    ODC_ODbL = "ODC_ODbL"
    OTHER = "OTHER"


def validate_geographical_code(v: str | None) -> str | None:
    """An ISO 3166-1 alpha-2 country code, or one of the continent names."""
    continents = [
        "Africa",
        "Antarctica",
        "Asia",
        "Europe",
        "North America",
        "Oceania",
        "South America",
        "World",
    ]

    if v:
        if pycountry.countries.get(alpha_2=v) is None and v not in continents:
            raise ValueError(f"The passed country {v} is not valid.")
    return v


class DatasetProvenance(BaseModel):
    """What describes a whole acquisition — the bundle scope.

    Importers write what the source states about itself; the rest is authored
    by the owner, because no source states a licence or a lineage in a form
    that can be trusted without a human.
    """

    lineage: str | None = Field(
        None, description="Source of the data and its derivation", max_length=500
    )
    geographical_code: str | None = Field(
        None,
        description="ISO 3166-1 alpha-2 country code, or a continent name",
        max_length=13,
    )
    distributor_name: str | None = Field(
        None, description="Entity distributing the data", max_length=500
    )
    distributor_email: EmailStr | None = Field(
        None, description="Contact for the distributor"
    )
    distribution_url: str | None = Field(None, description="URL to the distribution")
    license: DataLicense | None = Field(None, description="License of the data")
    attribution: str | None = Field(
        None, description="Attribution required by the source", max_length=500
    )
    data_reference_year: int | None = Field(
        None, description="Reference year of the data"
    )

    @field_validator("geographical_code", mode="after")
    @classmethod
    def geographical_code_valid(
        cls: type["DatasetProvenance"], value: str | None
    ) -> str | None:
        return validate_geographical_code(value)
