from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app.models import Product

def seed_products():
    db = SessionLocal()
    try:
        # Define default products
        products_data = [
            {
                "name": "KYC Lookup",
                "description": "Access to KYC lookup services",
                "price": 0.0,
                "is_active": True
            },
            {
                "name": "Bulk SMS",
                "description": "Send bulk SMS messages",
                "price": 0.0,
                "is_active": True
            },
            {
                "name": "Collections",
                "description": "Request payments from others",
                "price": 0.0,
                "is_active": True
            },
            {
                "name": "Statements",
                "description": "Download account statements",
                "price": 0.0,
                "is_active": True
            },
            {
                "name": "Airtime",
                "description": "Buy airtime for yourself or others",
                "price": 0.0,
                "is_active": True
            }
        ]

        for p_data in products_data:
            product = db.query(Product).filter(Product.name == p_data["name"]).first()
            if not product:
                print(f"Creating product: {p_data['name']}")
                new_product = Product(**p_data)
                db.add(new_product)
            else:
                print(f"Product already exists: {p_data['name']}")
        
        db.commit()
        print("Product seeding completed successfully.")

    except Exception as e:
        print(f"Error seeding products: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Ensure tables exist (in case they don't)
    Base.metadata.create_all(bind=engine)
    seed_products()
