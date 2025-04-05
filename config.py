import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = 'dev-secret-key-123'  # Fixed key for development
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY')
    PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY')
    
    # Plan IDs (to be updated with actual Paystack plan IDs)
    PAYSTACK_PLAN_IDS = {
        'pro_monthly': 'PLN_xxx',
        'business_monthly': 'PLN_xxx'
    }
    
    # Feature flags
    ENABLE_WATERMARK = True
    ENABLE_PDF_EXPORT = True
    
    # Rate limiting
    FREE_WEEKLY_LIMIT = 3
    PRO_MONTHLY_LIMIT = 20
    BUSINESS_MONTHLY_LIMIT = 50
