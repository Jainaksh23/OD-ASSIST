import asyncio
import os
import sys

# Add the parent directory to sys.path so we can import from db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.db import engine, get_db
from db.models import FAQ, Base

async def seed_faqs():
    Base.metadata.create_all(engine)
    db = next(get_db())
    try:
        faq1 = FAQ(
            question="How does fee collection work?",
            answer="Fee collection is automated through the Od Assist portal. You can navigate to the Fees module to pay your outstanding balance.",
            category="Fees",
            display_order=0,
            is_published=True
        )
        faq2 = FAQ(
            question="What is the transport module setup?",
            answer="The transport module allows tracking of bus routes. Admins must assign buses to routes and students to buses in the Okie Dokie admin dashboard.",
            category="Transport",
            display_order=1,
            is_published=True
        )
        faq3 = FAQ(
            question="What is the new student admission process?",
            answer="New students must submit the online admission form along with their previous school records and identity proofs. Verification takes 3-5 business days.",
            category="Admissions",
            display_order=2,
            is_published=True
        )
        faq4 = FAQ(
            question="How is payroll processed?",
            answer="Payroll is processed on the last working day of the month. Payslips can be downloaded from the HR portal.",
            category="Payroll",
            display_order=3,
            is_published=False # Draft
        )
        db.add_all([faq1, faq2, faq3, faq4])
        db.commit()
        print("Successfully seeded 4 FAQs.")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(seed_faqs())
