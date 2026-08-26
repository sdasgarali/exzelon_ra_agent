"""Gateway-agnostic payment processing interface."""
from abc import ABC, abstractmethod
from typing import Optional
import structlog

logger = structlog.get_logger()


class PaymentGateway(ABC):
    """Abstract payment gateway interface."""

    @abstractmethod
    def create_checkout_session(
        self,
        invoice_id: int,
        amount_cents: int,
        currency: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        metadata: dict = None,
    ) -> dict:
        """Create a checkout/payment session. Returns dict with 'checkout_url' and 'session_id'."""
        ...

    @abstractmethod
    def verify_payment(self, payment_id: str) -> dict:
        """Verify a payment status. Returns dict with 'status', 'amount_cents', 'currency'."""
        ...

    @abstractmethod
    def create_customer(self, email: str, name: str, metadata: dict = None) -> str:
        """Create a customer in the gateway. Returns customer ID string."""
        ...

    @abstractmethod
    def refund_payment(self, payment_id: str, amount_cents: Optional[int] = None) -> dict:
        """Refund a payment (full or partial). Returns dict with 'refund_id', 'status'."""
        ...


class StripeGateway(PaymentGateway):
    """Stripe payment gateway implementation."""

    def __init__(self):
        import stripe
        from app.core.config import settings
        stripe.api_key = settings.STRIPE_SECRET_KEY
        self._stripe = stripe

    def create_checkout_session(
        self,
        invoice_id: int,
        amount_cents: int,
        currency: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        metadata: dict = None,
    ) -> dict:
        meta = {"invoice_id": str(invoice_id)}
        if metadata:
            meta.update(metadata)
        session = self._stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": currency.lower(),
                    "unit_amount": amount_cents,
                    "product_data": {"name": f"Invoice #{invoice_id}"},
                },
                "quantity": 1,
            }],
            mode="payment",
            customer_email=customer_email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=meta,
        )
        logger.info("Stripe checkout session created", session_id=session.id, invoice_id=invoice_id)
        return {"checkout_url": session.url, "session_id": session.id}

    def verify_payment(self, payment_id: str) -> dict:
        pi = self._stripe.PaymentIntent.retrieve(payment_id)
        return {
            "status": pi.status,
            "amount_cents": pi.amount,
            "currency": pi.currency,
            "payment_method": pi.payment_method,
        }

    def create_customer(self, email: str, name: str, metadata: dict = None) -> str:
        customer = self._stripe.Customer.create(
            email=email,
            name=name,
            metadata=metadata or {},
        )
        logger.info("Stripe customer created", customer_id=customer.id, email=email)
        return customer.id

    def refund_payment(self, payment_id: str, amount_cents: Optional[int] = None) -> dict:
        params = {"payment_intent": payment_id}
        if amount_cents is not None:
            params["amount"] = amount_cents
        refund = self._stripe.Refund.create(**params)
        logger.info("Stripe refund created", refund_id=refund.id, payment_id=payment_id)
        return {"refund_id": refund.id, "status": refund.status}

    # --- Recurring subscriptions (ELR-021) ---

    def create_subscription_checkout(
        self, price_id: str, customer_email: str, success_url: str, cancel_url: str,
        metadata: dict = None,
    ) -> dict:
        """Start a Checkout Session in subscription mode. Returns checkout_url + session_id."""
        session = self._stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=customer_email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata or {},
            # Propagate metadata onto the Subscription too, so subscription.* webhook
            # events can resolve the owning tenant without a separate lookup.
            subscription_data={"metadata": metadata or {}},
        )
        logger.info("Stripe subscription checkout created", session_id=session.id, price=price_id)
        return {"checkout_url": session.url, "session_id": session.id}

    def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> dict:
        if at_period_end:
            sub = self._stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
        else:
            sub = self._stripe.Subscription.delete(subscription_id)
        return {"id": sub.id, "status": sub.status,
                "cancel_at_period_end": getattr(sub, "cancel_at_period_end", False)}

    def get_subscription(self, subscription_id: str) -> dict:
        sub = self._stripe.Subscription.retrieve(subscription_id)
        return {"id": sub.id, "status": sub.status,
                "current_period_end": getattr(sub, "current_period_end", None),
                "cancel_at_period_end": getattr(sub, "cancel_at_period_end", False)}


class ManualGateway(PaymentGateway):
    """No-op gateway for manual/offline payments."""

    def create_checkout_session(self, invoice_id, amount_cents, currency,
                                customer_email, success_url, cancel_url, metadata=None) -> dict:
        return {"checkout_url": None, "session_id": None, "message": "Manual payment — no online checkout"}

    def verify_payment(self, payment_id: str) -> dict:
        return {"status": "manual", "amount_cents": 0, "currency": "USD"}

    def create_customer(self, email: str, name: str, metadata: dict = None) -> str:
        return f"manual_{email}"

    def refund_payment(self, payment_id: str, amount_cents: Optional[int] = None) -> dict:
        return {"refund_id": None, "status": "manual_refund"}


def get_payment_gateway() -> PaymentGateway:
    """Factory: return Stripe gateway if configured, else Manual."""
    from app.core.config import settings
    if settings.STRIPE_SECRET_KEY:
        return StripeGateway()
    return ManualGateway()
