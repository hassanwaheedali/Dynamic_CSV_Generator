"""Dataclasses for the whole pipeline.

Design rule enforced by construction (spec section 0): there is exactly **one**
platform-agnostic ``ProductRecord`` per input row, and the two output rows are
thin projections of it (``DigiOutputRow`` / ``AlfaOutputRow``).  Shared facts
(Title, Description, SKU, price, images, ...) live on ``ProductRecord`` only, so
the DigiMall and Alfa files can never silently drift apart on a shared value.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InputRow:
    """One raw source row, exactly as read from the input sheet."""

    row_number: int
    title: str
    description: str
    sell_price: str
    original_price: str
    categories: str
    brand: str
    image: str
    vendor: str  # deliberately ignored downstream -- see VENDOR_DIGI / VENDOR_ALFA
    weight: str = ""       # optional "Weight" column; when absent the Description is read instead
    weight_unit: str = ""  # optional "Weight Unit" column


@dataclass(frozen=True)
class ResolvedBrand:
    """One brand string resolved independently against both platform lists."""

    raw: str
    normalized: str
    digi_id: int | None
    alfa_id: int | None


@dataclass(frozen=True)
class ResolvedCategory:
    """One breadcrumb string resolved independently against both platforms.

    ``digi_path`` is DigiMall's full underscore-joined root-to-leaf path
    (e.g. ``11639_11643_11661_11669``); ``alfa_id`` is Alfa's bare leaf id
    (e.g. ``11509``).  The two shapes are structurally different and are never
    interchangeable.
    """

    raw: str
    digi_path: str | None
    alfa_id: str | None
    matched_key: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class SpecRow:
    """One ``Label: Value`` row of the Description specification table."""

    label: str
    value: str
    is_warranty: bool = False


@dataclass(frozen=True)
class DescriptionBundle:
    """Everything section 8 builds once per product.

    ``short_description`` is built for every product but only ever written into
    the DigiMall file (Alfa's schema has no such column).
    """

    branch: str
    description_html: str
    short_description: str
    short_description_bullets: int
    tags: list[str]
    seo_title: str
    seo_description: str
    spec_rows: list[SpecRow]
    key_features: list[str]
    warranty_rows: list[SpecRow]
    thin: bool


@dataclass(frozen=True)
class ProductRecord:
    """The single resolved record shared by both platform projections."""

    row_number: int
    source: InputRow

    # --- shared identity -------------------------------------------------
    title: str
    product_type: str
    product_type_inferred: bool
    description: DescriptionBundle
    brand: ResolvedBrand
    category: ResolvedCategory

    # --- shared commercial fields ---------------------------------------
    images: str
    option1_name: str
    option1_value: str
    option2_name: str
    option2_value: str
    option3_name: str
    option3_value: str
    sku: str
    barcode: str
    bin_number: str
    handle: str
    weight: str
    weight_unit: str
    variant_price: int
    variant_compare_at_price: int
    variant_quantity: int

    # --- platform-only values (DigiMall) --------------------------------
    attributes: dict[str, str] = field(default_factory=dict)

    # --- provenance used by the QC report --------------------------------
    model: str = ""
    model_source: str = ""
    model_confidence: str = "none"
    warranty_source: str = "none"
    variant_suffix: str = ""
    handle_deduped: bool = False


@dataclass(frozen=True)
class DigiOutputRow:
    """Projection of a ProductRecord into DigiMall's 66-column schema (2A)."""

    values: dict[str, str]


@dataclass(frozen=True)
class AlfaOutputRow:
    """Projection of a ProductRecord into Alfa's 28-column schema (2B)."""

    values: dict[str, str]
