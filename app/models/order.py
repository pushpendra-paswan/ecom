from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_payment', 'paid', 'shipped', 'delivered', 'cancelled')",
            name="ck_orders_status",
        ),
        CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_not_negative"),
        Index("ix_orders_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending_payment"
    )
    # Total in paise
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)

    # Copy of the shipping address (no foreign key, so old orders never change)
    shipping_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    shipping_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_city: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_state: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    shipping_country: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # The lines always come back in the order they were created
    items: Mapped[list["OrderItem"]] = relationship(order_by="OrderItem.id")
    payment: Mapped["Payment | None"] = relationship()


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("unit_price > 0", name="ck_order_items_unit_price_positive"),
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        # Postgres does not index foreign keys by itself. Every order page loads its lines by order_id.
        Index("ix_order_items_order_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # Snapshots of the product at the time of purchase
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # The product of this line (the seller dashboard reads its seller from here)
    product: Mapped["Product"] = relationship()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')", name="ck_payments_status"
        ),
        CheckConstraint("amount >= 0", name="ck_payments_amount_not_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # unique=True means one payment per order
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True, nullable=False)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Set when a refund was made (empty if Stripe said the charge was already refunded)
    stripe_refund_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, server_default="inr")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# Newest-first order lists (the seller and admin dashboards) read the first rows of this index instead of
# sorting every order (measured in PROJECT_CONTEXT.md, "Performance review")
Index("ix_orders_created_at_id", Order.created_at.desc(), Order.id.desc())

# The customer's own order list (newest first). The user_id column comes first, so this index also does the
# job of the old ix_orders_user_id, which was dropped. Without it the planner sometimes walked the index
# above for a customer's list (measured: 0.2 ms became 1.0 ms), with it the list takes 0.04 ms.
Index("ix_orders_user_id_created_at_id", Order.user_id, Order.created_at.desc(), Order.id.desc())
