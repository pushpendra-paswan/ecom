# Import every model here so Alembic and Base.metadata can see all the tables
from app.models.cart import Cart, CartItem
from app.models.catalog import Category, Product
from app.models.order import Order, OrderItem, Payment
from app.models.user import Address, User
