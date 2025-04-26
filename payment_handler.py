import os
import requests
from typing import Dict, Optional, Tuple
import json

class PaystackHandler:
    def __init__(self):
        """Initialize Paystack payment handler."""
        self.api_key = os.getenv('PAYSTACK_SECRET_KEY')
        if not self.api_key:
            raise ValueError("Paystack API key not found in environment variables")
        
        self.base_url = "https://api.paystack.co"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def initialize_payment(self, email: str, amount: float) -> Tuple[bool, str, Optional[str]]:
        """
        Initialize a payment transaction with Paystack.
        
        Args:
            email: Customer's email address
            amount: Amount to charge in the smallest currency unit (kobo for NGN, pesewas for GHS)
            
        Returns:
            Tuple of (success: bool, message: str, authorization_url: Optional[str])
        """
        try:
            url = f"{self.base_url}/transaction/initialize"
            payload = {
                "email": email,
                "amount": int(amount * 100),  # Convert to kobo/pesewas
                "currency": "GHS",  # Change to your preferred currency
                "callback_url": os.getenv('PAYSTACK_CALLBACK_URL', 'http://localhost:5000/payment/callback')
            }

            response = requests.post(
                url,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                if result['status']:
                    return True, "Payment initialization successful", result['data']['authorization_url']
                return False, result.get('message', 'Payment initialization failed'), None
            
            return False, f"Payment initialization failed: {response.text}", None

        except Exception as e:
            return False, f"Error initializing payment: {str(e)}", None

    def verify_payment(self, reference: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Verify a payment transaction using its reference.
        
        Args:
            reference: Transaction reference to verify
            
        Returns:
            Tuple of (success: bool, message: str, transaction_data: Optional[Dict])
        """
        try:
            url = f"{self.base_url}/transaction/verify/{reference}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                result = response.json()
                if result['status'] and result['data']['status'] == 'success':
                    return True, "Payment verified successfully", result['data']
                return False, "Payment verification failed", None
            
            return False, f"Payment verification failed: {response.text}", None

        except Exception as e:
            return False, f"Error verifying payment: {str(e)}", None

class PaymentSession:
    def __init__(self, session_id: str):
        """Initialize payment session manager."""
        self.session_id = session_id
        self.payment_status = False
        self.slides_generated = 0
        self.max_free_slides = 5
        self.payment_required = False
        self.transaction_ref = None

    def increment_slides(self) -> Tuple[bool, str]:
        """
        Increment the number of slides generated and check if payment is required.
        
        Returns:
            Tuple of (can_continue: bool, message: str)
        """
        if self.payment_status:
            self.slides_generated += 1
            return True, "Payment completed, unlimited access granted"
        
        if self.slides_generated >= self.max_free_slides:
            self.payment_required = True
            return False, f"You've reached your free limit of {self.max_free_slides} slides. Please complete payment to continue."
        
        self.slides_generated += 1
        remaining = self.max_free_slides - self.slides_generated
        return True, f"You have {remaining} free slides remaining"

    def set_transaction_ref(self, ref: str) -> None:
        """Set the transaction reference for payment verification."""
        self.transaction_ref = ref

    def complete_payment(self) -> None:
        """Mark the payment as completed."""
        self.payment_status = True
        self.payment_required = False
