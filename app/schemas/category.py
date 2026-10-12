from pydantic import BaseModel, ConfigDict, Field


class CategoryRequest(BaseModel):
    # Remove spaces around every text value before it is checked
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class CategoryResponse(BaseModel):
    # Read the values straight from the Category model
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None


class CategoryListItemResponse(CategoryResponse):
    # Number of ACTIVE products in this category
    product_count: int
